# Deployment Guide - Get Your TTS Generator Online ASAP

## 🚀 Quick Local Test (2 minutes)

1. **Test the multi-user version:**
   ```bash
   python test_multiuser.py
   ```

2. **Open http://localhost:5000**

3. **Test login:** `test@example.com` / `password`

4. **Upload a video and generate content!**

## 🌐 Deploy to Production (15 minutes)

### Option 1: DigitalOcean App Platform (Easiest)

1. **Push to GitHub:**
   ```bash
   git add .
   git commit -m "Multi-user SaaS version"
   git push origin main
   ```

2. **Go to DigitalOcean App Platform:**
   - Connect your GitHub repo
   - Choose "Web Service"
   - Auto-detected: Python Flask
   - Environment variables:
     ```
     SECRET_KEY=your-production-secret-key-here
     DATABASE_URL=${db.DATABASE_URL}
     ```

3. **Add PostgreSQL database:**
   - In DigitalOcean: Add "Database" component
   - Choose PostgreSQL
   - It auto-connects via `${db.DATABASE_URL}`

4. **Deploy!** Takes ~5 minutes

### Option 2: Heroku (Also Easy)

1. **Install Heroku CLI and login**

2. **Create app:**
   ```bash
   heroku create your-app-name
   heroku addons:create heroku-postgresql:mini
   heroku config:set SECRET_KEY=your-secret-key-here
   ```

3. **Create Procfile:**
   ```
   web: gunicorn web_app_multiuser:app
   ```

4. **Deploy:**
   ```bash
   git add .
   git commit -m "Deploy to Heroku"
   git push heroku main
   heroku run python -c "from web_app_multiuser import app, db; app.app_context().push(); db.create_all()"
   ```

### Option 3: Railway (Very Simple)

1. **Connect GitHub to Railway.app**
2. **Environment variables:**
   ```
   SECRET_KEY=your-secret-key
   DATABASE_URL=postgresql://... (Railway provides this)
   ```
3. **Auto-deploys from GitHub!**

## 🔧 Production Environment Variables

```bash
# Required
SECRET_KEY=your-very-secure-secret-key-here
DATABASE_URL=postgresql://user:pass@host:port/dbname

# Optional
FLASK_ENV=production
WEB_CONCURRENCY=2
```

## 📊 Post-Deployment Checklist

1. **Test user registration** at your new URL
2. **Upload a test video** and generate content
3. **Check database** - users should be saving
4. **Monitor logs** for any errors
5. **Set up domain** (if desired)

## 💰 Estimated Costs

### DigitalOcean
- **App**: $12/month (1GB RAM)
- **Database**: $15/month (PostgreSQL)
- **Total**: ~$27/month

### Heroku
- **App**: $7/month (Eco dyno)
- **Database**: $9/month (Mini PostgreSQL)
- **Total**: ~$16/month

### Railway
- **Usage-based**: ~$5-20/month depending on traffic

## 🔒 Security Notes

1. **Change SECRET_KEY** in production
2. **Use HTTPS** (most platforms provide this free)
3. **Database backups** (enable on hosting platform)
4. **Monitor usage** to prevent abuse

## 🚨 Quick Fixes for Common Issues

### "Database not found"
```bash
# In production console:
python -c "from web_app_multiuser import app, db; app.app_context().push(); db.create_all()"
```

### "Module not found"
- Check `requirements.txt` is complete
- Verify `PYTHONPATH` in production

### "Files not uploading"
- Check file permissions in `/tmp` directory
- Verify disk space available

### "Videos not processing"
- Check ffmpeg is installed on production server
- Verify background workers are running

## 🎯 Next Steps After Deployment

1. **Add your domain** (Namecheap, GoDaddy, etc.)
2. **Set up monitoring** (Sentry for errors)
3. **Add Stripe** for billing (when ready)
4. **Optimize performance** based on usage

---

**🎉 You'll have a working multi-user video generator online in under 20 minutes!**

**Your users can now:**
- ✅ Register accounts
- ✅ Upload their videos  
- ✅ Generate AI-enhanced shorts
- ✅ Download results
- ✅ Track their usage

**Next: Add billing when you're ready to monetize! 💰**
