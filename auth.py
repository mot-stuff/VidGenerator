from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from models import User, db

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.is_json:
            # API login
            data = request.get_json()
            email = data.get('email')
            password = data.get('password')
        else:
            # Form login
            email = request.form.get('email')
            password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user, remember=True)
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
            if request.is_json:
                return jsonify({'success': False, 'error': error_msg}), 401
            flash(error_msg)
    
    return render_template('login.html')

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        if request.is_json:
            # API registration
            data = request.get_json()
            email = data.get('email')
            password = data.get('password')
        else:
            # Form registration
            email = request.form.get('email')
            password = request.form.get('password')
        
        # Check if user already exists
        if User.query.filter_by(email=email).first():
            error_msg = 'Email already registered'
            if request.is_json:
                return jsonify({'success': False, 'error': error_msg}), 400
            flash(error_msg)
            return render_template('register.html')
        
        # Create new user
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
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
