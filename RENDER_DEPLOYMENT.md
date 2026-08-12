# 🚀 Render Deployment Guide (100% Free & Persistent)

Render is the **ideal production host** for Python Flask + Twilio Voice applications because it provides persistent WSGI processes, free SSL HTTPS domains, and zero build errors.

---

### Step 1: Push Code to GitHub

Commit and push your updated codebase to GitHub:
```bash
git add .
git commit -m "Configure Render production deployment"
git push origin main
```

---

### Step 2: Create a New Web Service on Render

1. Go to [Render Dashboard](https://dashboard.render.com/).
2. Click **"New +"** → Select **"Web Service"**.
3. Connect your GitHub repository `Vikas-kumar-kumawat/callingAgent`.
4. Configure service details:
   - **Name**: `calling-agent`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`

---

### Step 3: Add Environment Variables in Render

Under **Environment Variables** in your Render service settings, add:

| Environment Variable | Value |
|---|---|
| `TWILIO_ACCOUNT_SID` | Your Twilio Account SID |
| `TWILIO_AUTH_TOKEN` | Your Twilio Auth Token |
| `TWILIO_PHONE_NUMBER` | Your Twilio Phone Number (e.g. `+19164356173`) |
| `GEMINI_API_KEY` | Your Gemini API Key |
| `GEMINI_MODEL` | `gemini-2.5-flash` |

---

### Step 4: Click "Create Web Service" 🎉

Render will build and deploy your app in ~1-2 minutes. Once finished, Render gives you a permanent HTTPS URL, such as:
`https://calling-agent.onrender.com`

All Twilio Webhooks (`/api/twilio/voice` & `/api/twilio/feedback`) will now run **100% reliably on Render**!
