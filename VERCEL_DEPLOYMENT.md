# 🚀 Vercel Production Deployment Guide

Your project is **100% Vercel & GitHub ready**. Follow these 4 simple steps to deploy:

---

### Step 1: Push Code to GitHub

Open terminal and push your repository to GitHub:
```bash
git add .
git commit -m "Prepare production build for Vercel"
git push origin main
```

---

### Step 2: Import Repository in Vercel

1. Go to [Vercel Dashboard](https://vercel.com/new).
2. Click **"Import"** next to your GitHub repository `calling-agent`.
3. Vercel will automatically detect `vercel.json` and Python backend.

---

### Step 3: Configure Environment Variables in Vercel

Under **Environment Variables** in Vercel settings, add the following key-value pairs:

| Key | Value |
|---|---|
| `TWILIO_ACCOUNT_SID` | Your Twilio Account SID |
| `TWILIO_AUTH_TOKEN` | Your Twilio Auth Token |
| `TWILIO_PHONE_NUMBER` | Your Twilio Phone Number (e.g. `+19164356173`) |
| `GEMINI_API_KEY` | Your Gemini API Key |
| `GEMINI_MODEL` | `gemini-2.5-flash` |

> 💡 **Note**: You do **NOT** need to set `BASE_URL` on Vercel! `app.py` automatically detects your live Vercel domain (e.g., `https://your-app.vercel.app`) dynamically on every request.

---

### Step 4: Click Deploy 🎉

Click **Deploy**. Once completed, Vercel will give you a live production URL like:
`https://calling-agent.vercel.app`

All Twilio Webhooks (`/api/twilio/voice` & `/api/twilio/feedback`) will now run on production serverless HTTPS smoothly!
