# VPS Deployment Guide - Full Control Video Processing

## 🚀 Quick VPS Setup (20 minutes to live)
# how to update and restart since we are deployed
cd /var/www/tts-generator
git status
git restore templates/base.html
git pull
sudo systemctl restart tts-generator
sudo systemctl reload nginx


### Step 1: Create VPS
1. **Go to [DigitalOcean](https://digitalocean.com)**
2. **Create Droplet:**
   - **Image**: Ubuntu 22.04 LTS
   - **Size**: Basic $6/month (1GB RAM)
   - **Region**: Closest to you
   - **Authentication**: SSH Key or Password

### Step 2: Initial Server Setup
```bash
# SSH into your server
ssh root@your-server-ip

# Update system
apt update && apt upgrade -y

# Install Python and dependencies
apt install -y python3 python3-pip python3-venv nginx postgresql postgresql-contrib

# Install video processing dependencies
apt install -y ffmpeg imagemagick

# Fonts (for consistent caption sizing on Linux)
apt install -y fonts-dejavu-core fonts-liberation

# Install Node.js (for any frontend builds)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
apt install -y nodejs
```

### Step 3: Setup PostgreSQL
```bash
# Switch to postgres user
sudo -u postgres psql

# In PostgreSQL prompt:
CREATE DATABASE tts_saas;
CREATE USER tts_user WITH ENCRYPTED PASSWORD 'Tbalty1212!';
GRANT ALL PRIVILEGES ON DATABASE tts_saas TO tts_user;
\q
```

### Step 4: Deploy Your App
```bash
# Create app directory
mkdir /var/www/tts-generator
cd /var/www/tts-generator

# Clone your code (or upload via SCP)
git clone https://github.com/mot-stuff/VidGenerator.git .

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cat > .env << EOF
SECRET_KEY=your-super-secure-secret-key-here
DATABASE_URL=postgresql://tts_user:your-secure-password@localhost/tts_saas
FLASK_ENV=production
EOF

# Initialize database
python web_app_multiuser.py &
# Let it create tables, then Ctrl+C
```

### Step 5: Setup Gunicorn Service
```bash
# Create systemd service
cat > /etc/systemd/system/tts-generator.service << EOF
[Unit]
Description=TTS Video Generator
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/tts-generator
Environment="PATH=/var/www/tts-generator/venv/bin"
ExecStart=/var/www/tts-generator/venv/bin/gunicorn --workers 2 --bind unix:tts-generator.sock -m 007 web_app_multiuser:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Start and enable service
systemctl start tts-generator
systemctl enable tts-generator
```

### Step 6: Setup Nginx
```bash
# Create nginx config
cat > /etc/nginx/sites-available/tts-generator << EOF
server {
    listen 80;
    server_name your-domain.com;  # Replace with your domain

    location / {
        include proxy_params;
        proxy_pass http://unix:/var/www/tts-generator/tts-generator.sock;
        client_max_body_size 2G;  # Allow large video uploads
        client_body_timeout 300s;
        send_timeout 300s;
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }
}
EOF

# Enable site
ln -s /etc/nginx/sites-available/tts-generator /etc/nginx/sites-enabled
rm /etc/nginx/sites-enabled/default

# Test and restart nginx
nginx -t
systemctl restart nginx
```

### Step 7: Setup Domain (Optional)
1. **Point your domain to the server IP**
2. **Install SSL with Let's Encrypt:**
```bash
apt install certbot python3-certbot-nginx
certbot --nginx -d  mindsrot.app
```

## 🎯 **Benefits of This Setup:**

### **Cost**: ~$6/month total
### **Performance**: Dedicated resources
### **Control**: Install anything you need
### **Reliability**: No platform restrictions

## 🔧 **File Permissions Setup:**
```bash
# Set proper ownership
chown -R www-data:www-data /var/www/tts-generator
chmod -R 755 /var/www/tts-generator

# Create upload directories
mkdir -p /var/www/tts-generator/user_data
chown -R www-data:www-data /var/www/tts-generator/user_data
```

## 📊 **Monitoring & Maintenance:**
```bash
# Check app status
systemctl status tts-generator

# View logs
journalctl -u tts-generator -f

# Restart app
systemctl restart tts-generator

# Update app
cd /var/www/tts-generator
git pull
systemctl restart tts-generator
```

## 🚨 **Backup Strategy:**
```bash
# Database backup (daily cron)
0 2 * * * pg_dump tts_saas > /backups/tts_saas_$(date +\%Y\%m\%d).sql

# User files backup
rsync -av /var/www/tts-generator/user_data/ /backups/user_data/
```

---

**🎉 Result: Full-featured video processing app for $6/month!**

**vs Platform Costs:**
- Railway: $20-50/month
- Heroku: $16-25/month  
- DigitalOcean App: $27/month
- **VPS**: $6/month ✅
