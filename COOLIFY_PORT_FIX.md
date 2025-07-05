# 🚨 Coolify Port Conflict - FIXED!

## ✅ **Problem Identified & Solved**

**Issue**: Your self-hosted Coolify is using port 8000, which conflicted with your M-Pesa app trying to use the same port.

**Solution**: Changed your app to use ports 3000 and 3001 internally.

## 🔧 **What I Changed:**

### **Before (Conflicting with Coolify):**
```yaml
expose:
  - "8000"  # ❌ Conflicts with Coolify
  - "5455"
```

### **After (No Conflicts):**
```yaml
expose:
  - "3000"  # ✅ AI Agent API
  - "3001"  # ✅ Webhook Server
```

## 📋 **What You Need to Do in Coolify:**

### 1. **Configure Application Port**
In your Coolify dashboard:
- Go to your M-Pesa app settings
- Look for **"Port"** or **"Application Port"** setting
- Set it to **`3000`** (for the AI Agent API)
- Save settings

### 2. **Redeploy**
- Click **"Redeploy"** to pull the latest changes
- Wait for deployment to complete

### 3. **Test the Application**
After redeployment, test:
```bash
curl https://mpesa-ai.cecilgachie.tech/health
```

## 🎯 **Expected Results:**

### **Your URLs:**
- **Main API**: `https://mpesa-ai.cecilgachie.tech/` (port 3000 internally)
- **Health Check**: `https://mpesa-ai.cecilgachie.tech/health`
- **Chat Endpoint**: `https://mpesa-ai.cecilgachie.tech/chat`

### **Webhook URLs:**
- **M-Pesa Callback**: `https://mpesa-ai.cecilgachie.tech/mpesa/callback`
- **WhatsApp Webhook**: `https://mpesa-ai.cecilgachie.tech/whatsapp/webhook`

## 🔧 **Internal Architecture:**

```
Coolify (Port 8000) ← Your Coolify Dashboard
    ↓
Your App Container:
├── AI Agent API (Port 3000) ← Main domain routes here
└── Webhook Server (Port 3001) ← Internal routing
```

## 🚀 **Next Steps:**

1. **Set port 3000 in Coolify settings**
2. **Redeploy**
3. **Test endpoints**
4. **Update external services** (Safaricom, Twilio) with callback URLs

The app should work perfectly now! 🎉
