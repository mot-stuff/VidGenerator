#!/usr/bin/env python3
"""
Test the multi-user app locally
"""

import os
from web_app_multiuser import app, db

if __name__ == '__main__':
    # Create .env file if it doesn't exist
    if not os.path.exists('.env'):
        with open('.env', 'w') as f:
            f.write("""SECRET_KEY=dev-secret-key-change-in-production
DATABASE_URL=sqlite:///tts_saas.db
FLASK_ENV=development
""")
        print("✅ Created .env file")
    
    with app.app_context():
        # Create database tables
        db.create_all()
        print("✅ Database tables created")
        
        # Create test user if none exist
        from models import User
        if not User.query.first():
            test_user = User(email='test@example.com')
            test_user.set_password('password')
            db.session.add(test_user)
            db.session.commit()
            print("✅ Created test user: test@example.com / password")
    
    print("\n🚀 Multi-User TTS Shorts Generator")
    print("📱 Open: http://localhost:5000")
    print("👤 Test login: test@example.com / password")
    print("🛑 Press Ctrl+C to stop\n")
    
    app.run(debug=True, host='127.0.0.1', port=5000)
