# SaaS Transition - Immediate Action Plan

## 🚀 Week 1-2: Foundation Setup

### Day 1-3: Development Environment
- [ ] **Set up PostgreSQL locally**
  ```bash
  # Install PostgreSQL
  brew install postgresql  # macOS
  # or
  sudo apt install postgresql  # Ubuntu
  
  # Create database
  createdb tts_saas_dev
  ```

- [ ] **Install additional dependencies**
  ```bash
  pip install fastapi uvicorn sqlalchemy psycopg2-binary alembic python-jose passlib bcrypt stripe python-multipart
  ```

- [ ] **Set up environment variables**
  ```bash
  # Create .env file
  DATABASE_URL=postgresql://username:password@localhost/tts_saas_dev
  SECRET_KEY=your-secret-key-here
  STRIPE_SECRET_KEY=sk_test_...
  STRIPE_PUBLISHABLE_KEY=pk_test_...
  ```

### Day 4-7: Basic Auth Implementation
- [ ] **Create user models**
  - User table with id, email, password_hash, created_at
  - Subscription table with user_id, plan, status, expires_at
  - Usage table with user_id, videos_used, reset_date

- [ ] **Implement authentication endpoints**
  - POST /auth/register
  - POST /auth/login  
  - POST /auth/logout
  - GET /auth/me

- [ ] **Add JWT middleware**
  - Token generation and validation
  - Protected route decorator
  - User context in requests

### Day 8-14: Multi-Tenant File System
- [ ] **Implement user-isolated storage**
  ```python
  # Structure: users/{user_id}/videos/, users/{user_id}/temp/
  def get_user_directory(user_id: str, subdir: str = "") -> Path:
      return Path(f"user_data/{user_id}/{subdir}")
  ```

- [ ] **Update video processing**
  - Pass user_id to all video functions
  - Store files in user-specific directories
  - Update YouTube manager to be per-user

## 🎯 Week 3-4: Basic Billing

### Stripe Integration
- [ ] **Create Stripe products and prices**
  ```python
  # In Stripe dashboard, create:
  # - Free tier (0 price)
  # - Starter ($19/month, 50 videos)
  # - Pro ($49/month, 200 videos)
  ```

- [ ] **Implement subscription flow**
  - Checkout session creation
  - Webhook handling for subscription updates
  - Usage quota enforcement

### Basic Dashboard
- [ ] **User dashboard page**
  - Current subscription status
  - Videos used this month
  - Recent video history
  - Billing management

## 🔧 Quick Development Tips

### Database Setup (SQLAlchemy + Alembic)
```python
# models/user.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

### FastAPI Auth Decorator
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def get_current_user(token: str = Depends(security)):
    # Verify JWT token and return user
    pass

# Usage in routes
@app.get("/api/videos")
async def get_videos(user: User = Depends(get_current_user)):
    return get_user_videos(user.id)
```

### Usage Tracking Middleware
```python
@app.middleware("http")
async def track_usage(request: Request, call_next):
    if "/api/generate" in str(request.url):
        user = get_user_from_request(request)
        if not check_user_quota(user.id):
            raise HTTPException(429, "Monthly quota exceeded")
        increment_user_usage(user.id)
    return await call_next(request)
```

## 📊 MVP Feature Priority

### Must Have (Week 1-4)
1. ✅ User registration/login
2. ✅ Basic video generation with user isolation
3. ✅ Simple usage quotas
4. ✅ Stripe subscription (basic)

### Should Have (Week 5-8)
1. ⭐ Password reset flow
2. ⭐ Email verification
3. ⭐ Better dashboard UI
4. ⭐ Usage analytics

### Nice to Have (Week 9-12)
1. 🎯 Team accounts
2. 🎯 API access
3. 🎯 White-label options
4. 🎯 Advanced billing features

## 🚨 Critical Decisions Needed

### 1. **Hosting Platform**
- **DigitalOcean App Platform**: Easiest, $25-50/month to start
- **AWS**: Most scalable, complex setup
- **Heroku**: Simple but expensive
- **Recommendation**: Start with DigitalOcean, migrate to AWS later

### 2. **TTS Strategy**
- **Current**: TikTok TTS (free but unreliable)
- **Option 1**: Add ElevenLabs API ($5-30/month per user)
- **Option 2**: Multiple providers with fallback
- **Recommendation**: Keep TikTok as free tier, add premium TTS for paid users

### 3. **File Storage**
- **Local files**: Won't scale, single point of failure
- **AWS S3**: $0.02/GB, industry standard
- **Cloudflare R2**: $0.015/GB, cheaper
- **Recommendation**: Start with S3, consider R2 for cost savings

### 4. **Database Strategy**
- **PostgreSQL on server**: Simple to start
- **Managed database**: More reliable, higher cost
- **Recommendation**: Local Postgres for development, managed for production

## 💰 Minimum Viable Budget

### Development (DIY)
- **Domain**: $15/year
- **SSL Certificate**: Free (Let's Encrypt)
- **Development tools**: $0 (all open source)

### Hosting (Month 1)
- **DigitalOcean Droplet**: $20/month
- **Managed PostgreSQL**: $15/month
- **S3 Storage**: $5-10/month
- **Total**: ~$50/month

### Services
- **Stripe**: 2.9% + $0.30 per transaction
- **Email service (SendGrid)**: Free for 100 emails/day
- **Monitoring (Sentry)**: Free tier available

### Total Monthly Cost: $50-100 until revenue starts

## 🎯 First Customer Strategy

### Target Audience
1. **Content creators** struggling with video editing
2. **Social media managers** needing bulk content
3. **Small businesses** wanting social media presence
4. **Podcasters** converting to video format

### Marketing Channels
1. **ProductHunt launch**: Free, high visibility
2. **Reddit communities**: r/ContentCreation, r/socialmedia
3. **Twitter/X**: Share progress updates, build in public
4. **YouTube tutorials**: "How to create shorts in 2 minutes"

### Launch Strategy
1. **Week 1**: Soft launch to friends/family (10 users)
2. **Week 2**: Small communities (50 users)
3. **Week 3**: ProductHunt launch (500+ signups)
4. **Week 4**: Optimize based on feedback

---

**Ready to start? Pick one item from Day 1-3 and begin today! 🚀**
