from datetime import datetime, timedelta
from typing import Optional
import re
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from models import User, AuthEvent, IPBan, db

auth = Blueprint('auth', __name__)

def _get_client_ip() -> str:
    # Prefer Cloudflare/forwarded headers if present, else remote_addr.
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        # first IP is the original client
        return xff.split(",")[0].strip()
    return (request.remote_addr or "unknown").strip()

def _is_ip_banned(ip: str) -> bool:
    if not ip or ip == "unknown":
        return False
    ban = IPBan.query.filter_by(ip=ip).first()
    if not ban:
        return False
    if ban.banned_until is None:
        return True
    try:
        return ban.banned_until > datetime.utcnow()
    except Exception:
        return True

def _rate_limit_exceeded(ip: str, action: str, email: Optional[str], max_count: int, window_s: int) -> bool:
    cutoff = datetime.utcnow() - timedelta(seconds=window_s)
    try:
        ip_count = AuthEvent.query.filter(
            AuthEvent.ip == ip,
            AuthEvent.action == action,
            AuthEvent.created_at >= cutoff,
        ).count()
        if ip_count >= max_count:
            return True

        if email:
            email_count = AuthEvent.query.filter(
                AuthEvent.email == email,
                AuthEvent.action == action,
                AuthEvent.created_at >= cutoff,
            ).count()
            return email_count >= max_count
        return False
    except Exception:
        return False

def _record_auth_event(ip: str, action: str, email: Optional[str]) -> None:
    try:
        db.session.add(AuthEvent(ip=ip, action=action, email=(email or None)))
        # Retain only recent history to prevent unbounded growth
        cutoff = datetime.utcnow() - timedelta(days=14)
        AuthEvent.query.filter(AuthEvent.created_at < cutoff).delete(synchronize_session=False)
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        ip = _get_client_ip()
        if _is_ip_banned(ip):
            msg = "Access denied."
            if request.is_json:
                return jsonify({"success": False, "error": msg}), 403
            flash(msg)
            return render_template('login.html'), 403
        if request.is_json:
            # API login
            data = request.get_json()
            email = data.get('email')
            password = data.get('password')
        else:
            # Form login
            email = request.form.get('email')
            password = request.form.get('password')

        email_norm = (email or "").strip().lower() or None
        # Rate limit login attempts to slow brute force / scripted abuse
        if _rate_limit_exceeded(ip=ip, action="login", email=email_norm, max_count=20, window_s=600):
            msg = "Too many login attempts. Please wait a few minutes."
            if request.is_json:
                return jsonify({"success": False, "error": msg}), 429
            flash(msg)
            return render_template('login.html'), 429
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user, remember=True)
            try:
                user.last_login_ip = ip
                db.session.commit()
            except Exception:
                try:
                    db.session.rollback()
                except Exception:
                    pass
            _record_auth_event(ip=ip, action="login", email=email_norm)
            if request.is_json:
                return jsonify({
                    'success': True,
                    'user': {
                        'email': user.email,
                        'subscription_tier': user.subscription_tier,
                        'videos_used': user.videos_used_this_month,
                        'quota_limit': user.get_quota_limit()
                    }
                })
            return redirect(url_for('dashboard'))
        else:
            error_msg = 'Invalid email or password'
            _record_auth_event(ip=ip, action="login", email=email_norm)
            if request.is_json:
                return jsonify({'success': False, 'error': error_msg}), 401
            flash(error_msg)
    
    return render_template('login.html')

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        ip = _get_client_ip()
        if _is_ip_banned(ip):
            msg = "Access denied."
            if request.is_json:
                return jsonify({"success": False, "error": msg}), 403
            flash(msg)
            return render_template('register.html'), 403
        if request.is_json:
            # API registration
            data = request.get_json()
            email = data.get('email')
            password = data.get('password')
            username = data.get('username')
        else:
            # Form registration
            email = request.form.get('email')
            password = request.form.get('password')
            username = request.form.get('username')

        email_norm = (email or "").strip().lower() or None
        # Rate limit registrations to prevent quota bypass by mass-account creation
        # - 3 registrations / 10 minutes per IP/email
        # - 10 registrations / day per IP/email
        if _rate_limit_exceeded(ip=ip, action="register", email=email_norm, max_count=3, window_s=600) or _rate_limit_exceeded(ip=ip, action="register", email=email_norm, max_count=10, window_s=86400):
            msg = "Too many accounts created from this network. Please try again later."
            if request.is_json:
                return jsonify({"success": False, "error": msg}), 429
            flash(msg)
            return render_template('register.html'), 429
        
        # Check if user already exists
        if User.query.filter_by(email=email).first():
            error_msg = 'Email already registered'
            _record_auth_event(ip=ip, action="register", email=email_norm)
            if request.is_json:
                return jsonify({'success': False, 'error': error_msg}), 400
            flash(error_msg)
            return render_template('register.html')

        username = (username or "").strip()
        if username:
            if len(username) < 3 or len(username) > 32:
                msg = "Username must be 3–32 characters"
                _record_auth_event(ip=ip, action="register", email=email_norm)
                if request.is_json:
                    return jsonify({"success": False, "error": msg}), 400
                flash(msg)
                return render_template('register.html')
            if not re.fullmatch(r"[A-Za-z0-9_]+", username):
                msg = "Username can only contain letters, numbers, and underscore"
                _record_auth_event(ip=ip, action="register", email=email_norm)
                if request.is_json:
                    return jsonify({"success": False, "error": msg}), 400
                flash(msg)
                return render_template('register.html')

            candidate = username.lower()
            exists = (
                db.session.query(User.id)
                .filter(db.func.lower(User.username) == candidate)
                .first()
                is not None
            )
            if exists:
                msg = "Username is already taken"
                _record_auth_event(ip=ip, action="register", email=email_norm)
                if request.is_json:
                    return jsonify({"success": False, "error": msg}), 409
                flash(msg)
                return render_template('register.html')
        
        # Create new user
        user = User(email=(email_norm or email))
        user.username = username or None
        user.set_password(password)
        user.last_login_ip = ip
        db.session.add(user)
        db.session.commit()
        _record_auth_event(ip=ip, action="register", email=email_norm)
        
        login_user(user)
        
        if request.is_json:
            return jsonify({
                'success': True,
                'user': {
                    'email': user.email,
                    'subscription_tier': user.subscription_tier,
                    'videos_used': user.videos_used_this_month,
                    'quota_limit': user.get_quota_limit()
                }
            })
        
        return redirect(url_for('dashboard'))
    
    return render_template('register.html')

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth.route('/api/user')
@login_required
def api_user():
    """Get current user info via API"""
    return jsonify({
        'email': current_user.email,
        'subscription_tier': current_user.subscription_tier,
        'videos_used': current_user.videos_used_this_month,
        'quota_limit': current_user.get_quota_limit(),
        'can_generate': current_user.can_generate_video()
    })
