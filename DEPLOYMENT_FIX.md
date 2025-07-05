# 🚨 Deployment Fix - Port Conflict Resolved

## ✅ **Problem Fixed!**

The deployment was failing because **port 8000 was already in use** on your Coolify server.

## 🔧 **What I Changed:**

### Before (Conflicting):
```yaml
ports:
  - "8000:8000"  # ❌ Port 8000 already in use
  - "5455:5455"  # ❌ Might also conflict
```

### After (Fixed):
```yaml
ports:
  - "3000:8000"  # ✅ External port 3000 → Internal port 8000
  - "3001:5455"  # ✅ External port 3001 → Internal port 5455
```

## 🎯 **Your New URLs Will Be:**

After redeployment:
- **AI Agent API**: `https://your-domain.com:3000`
- **Webhook Server**: `https://your-domain.com:3001`

## 📋 **What You Need to Do:**

### 1. **Redeploy in Coolify**
- Go back to your Coolify dashboard
- Click **"Redeploy"** (it will pull the latest changes)
- Wait for successful deployment

### 2. **Update Your Callback URL**
In Coolify environment variables, set:
```env
MPESA_CALLBACK_URL=https://your-domain.com:3001/mpesa/callback
```

### 3. **Update External Services**
- **Safaricom Portal**: `https://your-domain.com:3001/mpesa/callback`
- **Twilio Console**: `https://your-domain.com:3001/whatsapp/webhook`

### 4. **Update Mobile App**
Your friend should use:
```javascript
const API_BASE_URL = 'https://your-domain.com:3000';
```

## 🧪 **Test After Deployment:**

```bash
# Test AI Agent API
curl https://your-domain.com:3000/health

# Test Webhook Server
curl https://your-domain.com:3001/whatsapp/test
```

## 💡 **Why This Happened:**

Coolify servers often have services running on common ports like:
- Port 8000 (often used by other apps)
- Port 80/443 (web server)
- Port 22 (SSH)

Using ports 3000 and 3001 avoids these conflicts.

## 🚀 **Ready to Redeploy!**

The code has been pushed to GitHub. Just click **"Redeploy"** in Coolify and it should work now! 

The deployment should succeed this time because we're using available ports. 🎉
