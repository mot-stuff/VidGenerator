from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    # Admin / access control
    is_admin = db.Column(db.Boolean, default=False)

    # Abuse prevention / auditing
    last_login_ip = db.Column(db.String(64))

    # Daily quota (production)
    daily_quota = db.Column(db.Integer, default=3)
    daily_videos_used = db.Column(db.Integer, default=0)
    daily_last_reset_date = db.Column(db.Date, default=date.today)

    bonus_credits = db.Column(db.Integer, default=0)
    
    # Usage tracking
    videos_used_this_month = db.Column(db.Integer, default=0)
    last_reset_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Subscription info
    subscription_tier = db.Column(db.String(50), default='free')  # free, pro
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_quota_limit(self):
        """Get video quota based on subscription tier"""
        quotas = {
            'free': 5,
            'pro': 100
        }
        tier = (self.subscription_tier or 'free').strip().lower()
        # Backwards compatibility: older DBs may still contain "starter"
        if tier == 'starter':
            tier = 'free'
        return quotas.get(tier, 5)
    
    def can_generate_video(self):
        """Check if user can generate another video"""
        # Reset monthly usage if it's a new month
        now = datetime.utcnow()
        if (now.year, now.month) != (self.last_reset_date.year, self.last_reset_date.month):
            self.videos_used_this_month = 0
            self.last_reset_date = now
            db.session.commit()
        
        return self.videos_used_this_month < self.get_quota_limit()
    
    def increment_usage(self):
        """Increment video usage count"""
        self.videos_used_this_month += 1
        db.session.commit()

    def get_daily_quota(self) -> int:
        q = self.daily_quota
        if q is None:
            q = 3
        try:
            base = max(0, int(q))
        except Exception:
            base = 3

        tier = (self.subscription_tier or 'free').strip().lower()
        if tier == 'pro':
            return max(base, 12)
        return base

    def _reset_daily_usage_if_needed(self) -> None:
        today = datetime.utcnow().date()
        last = self.daily_last_reset_date
        if last != today:
            self.daily_videos_used = 0
            self.daily_last_reset_date = today

    def remaining_daily_quota(self) -> int:
        self._reset_daily_usage_if_needed()
        used = self.daily_videos_used or 0
        return max(0, self.get_daily_quota() - int(used))

    def can_generate_today(self, count: int = 1) -> bool:
        if self.is_admin:
            return True
        self._reset_daily_usage_if_needed()
        requested = max(1, int(count))
        bonus = self.bonus_credits or 0
        return (self.remaining_daily_quota() + int(bonus)) >= requested

    def consume_daily_quota(self, count: int = 1) -> None:
        self._reset_daily_usage_if_needed()
        requested = max(1, int(count))

        bonus = int(self.bonus_credits or 0)
        if bonus > 0:
            used_bonus = min(bonus, requested)
            self.bonus_credits = bonus - used_bonus
            requested -= used_bonus

        if requested <= 0:
            db.session.commit()
            return

        if self.daily_videos_used is None:
            self.daily_videos_used = 0
        self.daily_videos_used += requested
        db.session.commit()
    
    def __repr__(self):
        return f'<User {self.email}>'

class VideoJob(db.Model):
    """Track video processing jobs"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    text_content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default='pending')  # pending, processing, completed, failed
    stage = db.Column(db.String(64))
    progress = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)
    result_path = db.Column(db.String(255))
    
    user = db.relationship('User', backref=db.backref('video_jobs', lazy=True))
    
    def __repr__(self):
        return f'<VideoJob {self.id}: {self.status}>'


class RewardTicket(db.Model):
    id = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    redeemed_at = db.Column(db.DateTime, index=True)

    user = db.relationship('User', backref=db.backref('reward_tickets', lazy=True))


class AuthEvent(db.Model):
    """Track auth-related events for abuse prevention (DB-backed rate limiting)."""
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(64), nullable=False, index=True)
    action = db.Column(db.String(32), nullable=False, index=True)  # register, login
    email = db.Column(db.String(120), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        db.Index("ix_authevent_ip_action_created", "ip", "action", "created_at"),
        db.Index("ix_authevent_email_action_created", "email", "action", "created_at"),
    )


class IPBan(db.Model):
    """Block abusive traffic by IP."""
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(64), unique=True, nullable=False, index=True)
    reason = db.Column(db.String(255))
    banned_until = db.Column(db.DateTime)  # null = permanent
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
