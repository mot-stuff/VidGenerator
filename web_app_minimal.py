#!/usr/bin/env python3
"""
MINIMAL Multi-user App - Just to get Render working first
"""

import os
from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_login import LoginManager, login_required, current_user
from dotenv import load_dotenv

load_dotenv()

from models import db, User
from auth import auth

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///minimal.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Fix PostgreSQL URL
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://')

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

app.register_blueprint(auth)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('auth.login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

@app.route('/api/status')
@login_required
def get_status():
    return jsonify({'user': {'email': current_user.email}})

# Placeholder endpoints that work
@app.route('/api/upload_video', methods=['POST'])
@login_required
def upload_video():
    return jsonify({'message': 'Video processing coming soon!', 'file_id': 'test'})

@app.route('/api/generate_video', methods=['POST'])
@login_required  
def generate_video():
    return jsonify({'success': True, 'message': 'Video generation coming in next update!'})

@app.route('/api/list_files')
@login_required
def list_files():
    return jsonify({'files': []})

@app.route('/api/cleanup', methods=['POST'])
@login_required
def cleanup():
    return jsonify({'success': True})

def init_database():
    try:
        with app.app_context():
            db.create_all()
            if not User.query.first():
                test_user = User(email='test@example.com')
                test_user.set_password('password')
                db.session.add(test_user)
                db.session.commit()
                print("✅ Created test user")
    except Exception as e:
        print(f"Database error: {e}")

if __name__ == '__main__':
    init_database()
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

# For Gunicorn
init_database()
