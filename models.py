from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Usage tracking
    videos_used_this_month = db.Column(db.Integer, default=0)
    last_reset_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Subscription info (simple for now)
    subscription_tier = db.Column(db.String(50), default='free')  # free, starter, pro
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_quota_limit(self):
        """Get video quota based on subscription tier"""
        quotas = {
            'free': 5,
            'starter': 25,
            'pro': 100
        }
        return quotas.get(self.subscription_tier, 5)
    
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
    
    def __repr__(self):
        return f'<User {self.email}>'

class VideoJob(db.Model):
    """Track video processing jobs"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    text_content = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default='pending')  # pending, processing, completed, failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)
    result_path = db.Column(db.String(255))
    
    user = db.relationship('User', backref=db.backref('video_jobs', lazy=True))
    
    def __repr__(self):
        return f'<VideoJob {self.id}: {self.status}>'
