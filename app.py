import os
import uuid
import json
import re
import time
import threading
import subprocess
import urllib.request
from flask import Flask, request, jsonify, render_template, Response
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
from dotenv import load_dotenv

load_dotenv()

from google import genai

# Initialize Gemini Client
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
VOICE = "Google.en-US-Chirp3-HD-Aoede"
IS_VERCEL = bool(os.getenv("VERCEL") or os.getenv("VERCEL_ENV"))

app = Flask(__name__)

# Bypass warning headers for all responses
@app.after_request
def add_security_headers(response):
    response.headers["ngrok-skip-browser-warning"] = "true"
    response.headers["Bypass-Tunnel-Remainder"] = "true"
    return response

# =========================
# CONFIG & HYBRID DOMAIN ROUTING
# =========================
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

active_tunnel_url = ""
cf_process = None

def get_base_url():
    """Returns live public HTTPS URL.
    - Production (Vercel): uses request.host_url or VERCEL_URL or BASE_URL.
    - Local: uses active Cloudflare/tunnel URL."""
    # 1. Check Flask request context first
    try:
        if request and request.host:
            host = request.host.rstrip("/")
            if not host.startswith("http"):
                return f"https://{host}"
            return host
    except Exception:
        pass

    # 2. Check VERCEL_URL
    v_url = os.getenv("VERCEL_URL")
    if v_url:
        v_url = v_url.rstrip("/")
        return f"https://{v_url}" if not v_url.startswith("http") else v_url

    # 3. Check BASE_URL from env
    base_env = os.getenv("BASE_URL", "").strip().rstrip("/")
    if base_env:
        return base_env

    # 4. Fallback to active local tunnel URL
    global active_tunnel_url
    return active_tunnel_url

def update_env_base_url(live_url):
    """Auto-updates BASE_URL in .env file when running locally."""
    if IS_VERCEL or not live_url:
        return
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        updated = False
        new_lines = []
        for line in lines:
            if line.strip().startswith("BASE_URL="):
                new_lines.append(f"BASE_URL={live_url}\n")
                updated = True
            else:
                new_lines.append(line)
        
        if not updated:
            new_lines.append(f"\nBASE_URL={live_url}\n")
            
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        print(f"[Auto-Env] .env updated with BASE_URL={live_url}")
    except Exception as e:
        print(f"[Auto-Env Warning] {e}")

def start_local_cloudflare_tunnel():
    """Launches Cloudflare Free Tunnel locally (skipped automatically on Vercel)."""
    global active_tunnel_url, cf_process
    if IS_VERCEL:
        return None

    cf_bin = os.path.join(os.path.dirname(__file__), "cloudflared.exe")
    if not os.path.exists(cf_bin):
        return None

    print("[Auto-Tunnel] Starting Cloudflare Free Tunnel via cloudflared.exe...")
    try:
        cf_process = subprocess.Popen([cf_bin, "tunnel", "--url", "http://127.0.0.1:5000"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        start_t = time.time()
        while time.time() - start_t < 12:
            line = cf_process.stdout.readline()
            if line and "trycloudflare.com" in line:
                match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                if match:
                    found_url = match.group(0)
                    active_tunnel_url = found_url
                    print("\n==========================================")
                    print(f"[CLOUDFLARE TUNNEL SUCCESS] {found_url}")
                    print("==========================================\n")
                    update_env_base_url(found_url)
                    return found_url
    except Exception as err:
        print(f"[Auto-Tunnel Error] {err}")
    return None

def ensure_tunnel():
    """Master auto-tunnel initializer."""
    if IS_VERCEL:
        print("[Environment] Running on Vercel Serverless Production Engine.")
        return os.getenv("BASE_URL", "")

    cf_url = start_local_cloudflare_tunnel()
    if cf_url:
        return cf_url

    fallback = os.getenv("BASE_URL", "").strip().rstrip("/")
    global active_tunnel_url
    active_tunnel_url = fallback
    return fallback

BASE_URL = ensure_tunnel()
twilio = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN) else None

# =========================
# STORAGE & SEED DATA
# =========================
customers = [
    {
        "id": "c101",
        "name": "Sarah Jenkins",
        "phone": "+919057262630",
        "status": "completed",
        "feedback": ["The service was wonderful! Quick delivery and friendly staff.", "I would rate it 5 stars."],
        "rating": 5,
        "sentiment": "Positive",
        "transcript": [
            {"speaker": "ai", "text": "Hello! This is Sarah calling from Feedback Ops. How was your experience with our service?"},
            {"speaker": "customer", "text": "The service was wonderful! Quick delivery and friendly staff."},
            {"speaker": "ai", "text": "That is so great to hear! How many stars out of 5 would you give us?"},
            {"speaker": "customer", "text": "I would rate it 5 stars."},
            {"speaker": "ai", "text": "Thank you so much for your feedback! Have a lovely day. Goodbye."}
        ],
        "created_at": "2026-08-12 10:15",
        "last_call": "10:17 AM"
    },
    {
        "id": "c102",
        "name": "David Miller",
        "phone": "+19164356173",
        "status": "pending",
        "feedback": [],
        "rating": None,
        "sentiment": "Neutral",
        "transcript": [],
        "created_at": "2026-08-12 11:30",
        "last_call": None
    },
    {
        "id": "c103",
        "name": "Priya Sharma",
        "phone": "+919876543210",
        "status": "pending",
        "feedback": [],
        "rating": None,
        "sentiment": "Neutral",
        "transcript": [],
        "created_at": "2026-08-12 11:45",
        "last_call": None
    }
]

campaign_state = {
    "running": False,
    "current_id": None,
    "last_dialed": None
}

def find_customer(customer_id=None, phone=None):
    if customer_id:
        c = next((item for item in customers if item["id"] == customer_id), None)
        if c: return c
    if phone:
        clean_target = re.sub(r"\D", "", str(phone))
        for item in customers:
            clean_item = re.sub(r"\D", "", str(item.get("phone", "")))
            if clean_item and (clean_item.endswith(clean_target) or clean_target.endswith(clean_item)):
                return item
    return None

def generate_ai_response(customer_text, customer=None):
    """Generates conversational response via Gemini API with smart intelligent fallback."""
    ai_text = ""
    lower = customer_text.lower()
    
    if gemini:
        try:
            prompt = f"""
You are Sarah, a warm and polite customer feedback phone agent.
The customer said: "{customer_text}"

Rules:
1. Acknowledge what they said naturally.
2. If they haven't given a 1 to 5 star rating yet, ask for a star rating.
3. Keep your reply concise (maximum 20 words).
4. Speak naturally without markdown or internal labels.
"""
            res = gemini.models.generate_content(model=GEMINI_MODEL, contents=prompt)
            if res and res.text:
                ai_text = res.text.strip()
        except Exception as ex:
            print(f"[Gemini API Exception] {ex}")

    if not ai_text:
        nums = re.findall(r"\b([1-5])\b", customer_text)
        rating_num = int(nums[0]) if nums else (customer.get("rating") if customer else None)
        
        bye_words = ["bye", "goodbye", "thank you", "thanks", "that's all", "done", "no", "that is all"]
        if any(w in lower for w in bye_words):
            ai_text = "Thank you so much for your valuable feedback! Have a wonderful day. Goodbye!"
        elif rating_num:
            if rating_num >= 4:
                ai_text = f"Thank you so much for giving us {rating_num} stars! We are delighted to hear your feedback."
            else:
                ai_text = f"Thank you for your {rating_num} star rating. We sincerely apologize for any inconvenience and will work to improve."
        elif any(w in lower for w in ["good", "great", "excellent", "awesome", "amazing", "wonderful", "nice", "happy"]):
            ai_text = "That is so wonderful to hear! How many stars out of 5 would you give our service?"
        elif any(w in lower for w in ["bad", "poor", "slow", "worst", "terrible", "issue", "delay", "not good"]):
            ai_text = "We are truly sorry to hear that. How many stars out of 5 would you rate your overall experience?"
        else:
            ai_text = "Thank you for sharing that with us! How would you rate your overall experience from 1 to 5 stars?"

    return ai_text

# =========================
# CAMPAIGN WORKER THREAD (Only in non-Vercel environment)
# =========================
def campaign_loop():
    while True:
        try:
            if campaign_state["running"]:
                pending = next((c for c in customers if c["status"] == "pending"), None)
                if pending:
                    print(f"[Campaign Worker] Auto-dialing customer: {pending['name']} ({pending['phone']})")
                    campaign_state["current_id"] = pending["id"]
                    campaign_state["last_dialed"] = pending["name"]
                    
                    base = get_base_url()
                    voice_url = f"{base}/api/twilio/voice?customer_id={pending['id']}"
                    status_url = f"{base}/api/twilio/status?customer_id={pending['id']}"
                    
                    if twilio:
                        try:
                            pending["status"] = "calling"
                            call = twilio.calls.create(
                                to=pending["phone"],
                                from_=TWILIO_PHONE_NUMBER,
                                url=voice_url,
                                method="POST",
                                status_callback=status_url,
                                status_callback_method="POST",
                                status_callback_event=["initiated", "ringing", "answered", "completed"]
                            )
                            pending["call_sid"] = call.sid
                        except Exception as ex:
                            print(f"[Campaign Worker] Call creation failed: {ex}")
                            pending["status"] = "failed"
                    
                    time.sleep(25)
                else:
                    print("[Campaign Worker] All customers processed. Stopping campaign.")
                    campaign_state["running"] = False
                    campaign_state["current_id"] = None
        except Exception as err:
            print(f"[Campaign Worker Error] {err}")
        time.sleep(3)

if not IS_VERCEL:
    threading.Thread(target=campaign_loop, daemon=True).start()

# =========================
# FRONTEND & HEALTH
# =========================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "engine": "Gemini 2.5 Flash + Twilio Voice",
        "voice": VOICE,
        "environment": "Vercel Production" if IS_VERCEL else "Local Development",
        "base_url": get_base_url()
    })

# =========================
# CUSTOMERS API
# =========================
@app.route("/api/customers", methods=["GET"])
def get_customers():
    return jsonify(customers)

@app.route("/api/customers/<customer_id>", methods=["GET"])
def get_customer_detail(customer_id):
    c = find_customer(customer_id=customer_id)
    if not c:
        return jsonify({"success": False, "error": "Customer not found"}), 404
    return jsonify({"success": True, "customer": c})

@app.route("/api/customers", methods=["POST"])
def add_customer():
    data = request.get_json(force=True, silent=True) or {}
    name = str(data.get("name", "")).strip()
    phone = str(data.get("phone", "")).strip()

    if not name or not phone:
        return jsonify({"success": False, "error": "Name and phone number are required"}), 400

    existing = find_customer(phone=phone)
    if existing:
        return jsonify({"success": False, "error": f"Customer with phone {phone} already exists ({existing['name']})"}), 400

    new_id = f"c{int(time.time() % 100000)}"
    customer = {
        "id": new_id,
        "name": name,
        "phone": phone,
        "status": "pending",
        "feedback": [],
        "rating": None,
        "sentiment": "Neutral",
        "transcript": [],
        "created_at": time.strftime("%Y-%m-%d %H:%M"),
        "last_call": None
    }
    customers.append(customer)
    return jsonify({"success": True, "customer": customer}), 201

@app.route("/api/customers/<customer_id>", methods=["DELETE"])
def delete_customer(customer_id):
    global customers
    c = find_customer(customer_id=customer_id)
    if not c:
        return jsonify({"success": False, "error": "Customer not found"}), 404
    customers = [item for item in customers if item["id"] != customer_id]
    return jsonify({"success": True, "message": "Customer deleted successfully"})

@app.route("/api/seed", methods=["POST"])
def reset_seed_data():
    global customers
    customers.clear()
    customers.extend([
        {
            "id": "c101",
            "name": "Sarah Jenkins",
            "phone": "+919057262630",
            "status": "completed",
            "feedback": ["The service was wonderful! Quick delivery and friendly staff.", "I would rate it 5 stars."],
            "rating": 5,
            "sentiment": "Positive",
            "transcript": [
                {"speaker": "ai", "text": "Hello! This is Sarah calling from Feedback Ops. How was your experience with our service?"},
                {"speaker": "customer", "text": "The service was wonderful! Quick delivery and friendly staff."},
                {"speaker": "ai", "text": "That is so great to hear! How many stars out of 5 would you give us?"},
                {"speaker": "customer", "text": "I would rate it 5 stars."},
                {"speaker": "ai", "text": "Thank you so much for your feedback! Have a lovely day. Goodbye."}
            ],
            "created_at": time.strftime("%Y-%m-%d %H:%M"),
            "last_call": "Recent"
        },
        {
            "id": "c102",
            "name": "David Miller",
            "phone": "+19164356173",
            "status": "pending",
            "feedback": [],
            "rating": None,
            "sentiment": "Neutral",
            "transcript": [],
            "created_at": time.strftime("%Y-%m-%d %H:%M"),
            "last_call": None
        },
        {
            "id": "c103",
            "name": "Priya Sharma",
            "phone": "+919876543210",
            "status": "pending",
            "feedback": [],
            "rating": None,
            "sentiment": "Neutral",
            "transcript": [],
            "created_at": time.strftime("%Y-%m-%d %H:%M"),
            "last_call": None
        }
    ])
    return jsonify({"success": True, "message": "Sample data reset successfully", "customers": customers})

# =========================
# MAKE CALL API
# =========================
@app.route("/api/call", methods=["POST"])
def make_call():
    data = request.get_json(force=True, silent=True) or {}
    customer_id = data.get("customer_id")
    phone = data.get("phone")

    customer = find_customer(customer_id=customer_id, phone=phone)
    if customer_id and not customer:
        return jsonify({"success": False, "error": "Customer ID not found"}), 404

    target_phone = customer["phone"] if customer else phone
    if not target_phone:
        return jsonify({"success": False, "error": "Phone number or valid customer_id is required"}), 400

    base = get_base_url()
    cid_param = f"?customer_id={customer['id']}" if customer else f"?phone={urllib.parse.quote(target_phone)}"
    voice_url = f"{base}/api/twilio/voice{cid_param}"
    status_url = f"{base}/api/twilio/status{cid_param}"

    print(f"[Initiate Call] Dialing {target_phone} via Voice URL: {voice_url}")

    if not twilio:
        if customer:
            customer["status"] = "calling"
        return jsonify({
            "success": True,
            "simulated": True,
            "message": f"Twilio client not initialized with real SID/Token, simulated call status for {target_phone}."
        })

    try:
        call = twilio.calls.create(
            to=target_phone,
            from_=TWILIO_PHONE_NUMBER,
            url=voice_url,
            method="POST",
            status_callback=status_url,
            status_callback_method="POST",
            status_callback_event=["initiated", "ringing", "answered", "completed"]
        )

        if customer:
            customer["status"] = "calling"
            customer["call_sid"] = call.sid
            customer["last_call"] = time.strftime("%H:%M:%S")

        return jsonify({
            "success": True,
            "call_id": call.sid,
            "status": call.status,
            "message": f"AI call initiated to {customer['name'] if customer else target_phone}"
        })

    except Exception as e:
        print(f"[Call Exception] {e}")
        if customer:
            customer["status"] = "failed"
        return jsonify({"success": False, "error": str(e)}), 500

# =========================
# TWILIO VOICE WEBHOOK
# =========================
@app.route("/api/twilio/voice", methods=["POST", "GET"])
def twilio_voice():
    print("\n==========================================")
    print(">>> TWILIO VOICE WEBHOOK CONNECTED")
    print("==========================================")

    customer_id = request.args.get("customer_id")
    phone = request.args.get("phone") or request.form.get("To") or request.form.get("From")
    customer = find_customer(customer_id=customer_id, phone=phone)

    if customer:
        customer["status"] = "calling"

    base = get_base_url()
    cid_param = f"?customer_id={customer['id']}" if customer else ""
    feedback_url = f"{base}/api/twilio/feedback{cid_param}"

    response = VoiceResponse()

    greeting_text = f"Hello {customer['name'] if customer else ''}! This is Sarah calling from Customer Operations. We would love to get your quick feedback today. How was your recent experience with our service?"
    
    response.say(greeting_text, voice=VOICE)

    if customer:
        customer["transcript"] = [{"speaker": "ai", "text": greeting_text}]

    gather = response.gather(
        input="speech",
        action=feedback_url,
        method="POST",
        speech_timeout="auto",
        language="en-IN"
    )

    gather.say("Please tell me about your experience.", voice=VOICE)

    response.say("Thank you for your time. Goodbye!", voice=VOICE)
    response.hangup()

    return Response(str(response), status=200, content_type="text/xml")

# =========================
# TWILIO FEEDBACK WEBHOOK (AI CONVERSATION)
# =========================
@app.route("/api/twilio/feedback", methods=["POST"])
def twilio_feedback():
    print("\n>>> TWILIO FEEDBACK WEBHOOK HIT")

    customer_id = request.args.get("customer_id")
    called_phone = request.form.get("To") or request.form.get("From")
    customer_text = request.form.get("SpeechResult", "").strip()

    customer = find_customer(customer_id=customer_id, phone=called_phone)
    print(f"Customer: {customer['name'] if customer else 'Unknown'} | Said: {customer_text!r}")

    response = VoiceResponse()
    base = get_base_url()
    cid_param = f"?customer_id={customer['id']}" if customer else ""
    feedback_url = f"{base}/api/twilio/feedback{cid_param}"

    if not customer_text:
        response.say("I didn't quite catch that. Could you please tell me about your experience?", voice=VOICE)
        gather = response.gather(
            input="speech",
            action=feedback_url,
            method="POST",
            speech_timeout="auto",
            language="en-IN"
        )
        gather.say("I am listening.", voice=VOICE)
        return Response(str(response), status=200, content_type="text/xml")

    if customer:
        if not isinstance(customer.get("feedback"), list):
            customer["feedback"] = []
        customer["feedback"].append(customer_text)

        if not isinstance(customer.get("transcript"), list):
            customer["transcript"] = []
        customer["transcript"].append({"speaker": "customer", "text": customer_text})

        if customer.get("rating") is None:
            nums = re.findall(r"\b([1-5])\b", customer_text)
            if nums:
                customer["rating"] = int(nums[0])
                print(f"[Rating Extracted]: {customer['rating']} stars")

        pos_words = ["good", "great", "excellent", "amazing", "wonderful", "awesome", "fast", "love", "nice", "5", "4"]
        neg_words = ["bad", "poor", "terrible", "horrible", "slow", "delay", "worst", "hate", "1", "2"]
        lower = customer_text.lower()
        if any(w in lower for w in pos_words):
            customer["sentiment"] = "Positive"
        elif any(w in lower for w in neg_words):
            customer["sentiment"] = "Negative"
        else:
            customer["sentiment"] = "Neutral"

    ai_text = generate_ai_response(customer_text, customer)
    print(f"AI Response: {ai_text!r}")

    if customer:
        customer["transcript"].append({"speaker": "ai", "text": ai_text})

    bye_keywords = ["bye", "goodbye", "thank you", "thanks", "that's all", "done", "no", "that is all"]
    is_closing = any(w in customer_text.lower() for w in bye_keywords)

    response.say(ai_text, voice=VOICE)

    if is_closing or (customer and customer.get("rating") is not None and len(customer.get("feedback", [])) >= 2):
        response.say("Have a fantastic day! Goodbye.", voice=VOICE)
        response.hangup()
        if customer:
            customer["status"] = "completed"
    else:
        gather = response.gather(
            input="speech",
            action=feedback_url,
            method="POST",
            speech_timeout="auto",
            language="en-IN"
        )
        gather.say("Is there anything else you would like to add?", voice=VOICE)
        response.say("Thank you for your feedback! Goodbye.", voice=VOICE)
        response.hangup()

    return Response(str(response), status=200, content_type="text/xml")

# =========================
# TWILIO CALL STATUS WEBHOOK
# =========================
@app.route("/api/twilio/status", methods=["POST"])
def twilio_status():
    customer_id = request.args.get("customer_id")
    call_sid = request.form.get("CallSid", "")
    call_status = request.form.get("CallStatus", "")
    phone = request.form.get("To", "") or request.form.get("From", "")

    print(f"[STATUS CALLBACK] SID={call_sid} | Status={call_status} | Target={phone}")

    customer = find_customer(customer_id=customer_id, phone=phone)
    if customer:
        if call_status == "completed":
            customer["status"] = "completed"
        elif call_status in ("failed", "busy", "no-answer", "canceled"):
            customer["status"] = "failed"
        elif call_status in ("initiated", "ringing", "in-progress"):
            customer["status"] = "calling"

    return Response("OK", status=200)

# =========================
# CAMPAIGN API
# =========================
@app.route("/api/campaign", methods=["GET"])
def get_campaign():
    return jsonify({
        "running": campaign_state["running"],
        "current_id": campaign_state["current_id"],
        "last_dialed": campaign_state["last_dialed"]
    })

@app.route("/api/campaign/start", methods=["POST"])
def start_campaign():
    campaign_state["running"] = True
    print("[Campaign API] Campaign Started!")
    return jsonify({"success": True, "running": True, "message": "Autodialer campaign started"})

@app.route("/api/campaign/stop", methods=["POST"])
def stop_campaign():
    campaign_state["running"] = False
    campaign_state["current_id"] = None
    print("[Campaign API] Campaign Stopped!")
    return jsonify({"success": True, "running": False, "message": "Campaign stopped"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
