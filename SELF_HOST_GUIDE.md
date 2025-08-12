# Self-Hosting Guide - Run Your Video Generator at Home

## 🏠 Local Network Self-Hosting (Easiest)

### Step 1: Run Your App Locally
```bash
# In your VidGenerator folder
python web_app_multiuser.py
```

### Step 2: Access from Any Device on Your Network
- **From your computer**: http://localhost:5000
- **From phone/tablet**: http://YOUR_LOCAL_IP:5000
- **From other computers**: http://YOUR_LOCAL_IP:5000

### Find Your Local IP:
```bash
# Windows
ipconfig | findstr IPv4

# Mac/Linux  
ifconfig | grep inet
```

**Example**: If your IP is `192.168.1.100`, access from any device at:
`http://192.168.1.100:5000`

---

## 🌐 Internet Access (Advanced but Free)

### Option A: Ngrok (Instant Internet Access)
```bash
# Install ngrok
# Download from https://ngrok.com

# Run your app
python web_app_multiuser.py

# In another terminal
ngrok http 5000
```
**Result**: Get a public URL like `https://abc123.ngrok.io`

### Option B: Cloudflare Tunnel (Free & Permanent)
```bash
# Install cloudflared
# Download from https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/

# Run your app
python web_app_multiuser.py

# Create tunnel
cloudflared tunnel --url http://localhost:5000
```
**Result**: Get a permanent cloudflare URL

### Option C: Dynamic DNS + Router Port Forwarding
1. **Set up Dynamic DNS** (DuckDNS, No-IP - free)
2. **Forward port 5000** in your router
3. **Access via**: your-domain.duckdns.org:5000

---

## ⚙️ Self-Host Production Setup

### Step 1: Create Production Environment
```bash
# Create .env file
cat > .env << EOF
SECRET_KEY=your-super-secure-secret-key-here
DATABASE_URL=sqlite:///tts_saas.db
FLASK_ENV=production
EOF
```

### Step 2: Install Production Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Run as Service (Windows)
Create `start_server.bat`:
```batch
@echo off
cd /d "C:\path\to\your\VidGenerator"
python web_app_multiuser.py
pause
```

### Step 4: Run as Service (Mac/Linux)
Create `start_server.sh`:
```bash
#!/bin/bash
cd /path/to/your/VidGenerator
python web_app_multiuser.py
```

---

## 🔒 Security for Internet Access

### Basic Security Setup:
1. **Change default password** for test user
2. **Use strong SECRET_KEY** in .env
3. **Enable HTTPS** with ngrok/cloudflare
4. **Firewall rules** if needed

### Production Security:
```python
# Add to web_app_multiuser.py
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 minutes
```

---

## 📱 Mobile Access

**Perfect for:**
- Upload videos from your phone
- Generate content while away from computer
- Share access with family/friends on your network

**Usage**:
1. **Phone connects to your WiFi**
2. **Open browser**: `http://192.168.1.100:5000`
3. **Login and use full app!**

---

## 💻 Hardware Requirements

### Minimum:
- **RAM**: 4GB (for basic video processing)
- **Storage**: 10GB free space
- **CPU**: Any modern processor

### Recommended:
- **RAM**: 8GB+ (for faster processing)
- **Storage**: 50GB+ (for multiple large videos)
- **GPU**: NVIDIA GPU (for faster AI processing)

---

## 🎯 Benefits of Self-Hosting

### **Cost**: $0/month
### **Performance**: Use your full hardware
### **Privacy**: Data never leaves your computer
### **Customization**: Modify anything you want
### **Learning**: Full control and understanding

---

## 🚀 Quick Start Commands

```bash
# 1. Run the app
python web_app_multiuser.py

# 2. Find your IP
ipconfig | findstr IPv4

# 3. Access from any device
# http://YOUR_IP:5000

# 4. For internet access (optional)
ngrok http 5000
```

**🎉 You now have a professional video generator running from your home!**
