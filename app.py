import os
import re
import time
import json
import subprocess
import urllib.parse
import urllib.request
import threading
from typing import Dict, Any, List, Optional
from flask import Flask, request, jsonify, render_template, Response
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
from dotenv import load_dotenv
from google import genai

load_dotenv()

# Environment Detection
IS_RENDER = bool(os.getenv("RENDER") or os.getenv("RENDER_EXTERNAL_HOSTNAME"))
IS_VERCEL = bool(os.getenv("VERCEL") or os.getenv("VERCEL_ENV") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
IS_CLOUD_PROD = IS_RENDER or IS_VERCEL or (os.name != "nt")

# Client Initializations
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
gemini = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
twilio = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN) else None

app = Flask(__name__)


@app.after_request
def add_security_headers(response):
    response.headers["ngrok-skip-browser-warning"] = "true"
    response.headers["Bypass-Tunnel-Remainder"] = "true"
    return response


# =========================
# VOICE CATALOG & CONFIG
# =========================
VOICE_CATALOG: List[Dict[str, str]] = [
    # Female Voices
    {
        "id": "Google.en-US-Chirp3-HD-Aoede",
        "name": "Sarah (Chirp3 Ultra-HD Female - US)",
        "accent": "US English",
        "gender": "Female",
        "sample_text": "Hello! I am Sarah, your AI Voice Assistant. How can I help you today?",
    },
    {
        "id": "Google.en-US-Journey-F",
        "name": "Emma (Journey Neural Female - US)",
        "accent": "US English",
        "gender": "Female",
        "sample_text": "Hi there! I am Emma. I use hyper-realistic natural speech inflections and conversational dynamics.",
    },
    {
        "id": "Google.en-IN-Wavenet-D",
        "name": "Priya (Wavenet Neural Female - India)",
        "accent": "Indian English",
        "gender": "Female",
        "sample_text": "Namaste! I am Priya. I deliver warm, polite, and respectful customer feedback calls.",
    },
    {
        "id": "Google.en-GB-Studio-B",
        "name": "Victoria (Studio Premium Female - UK British)",
        "accent": "British English",
        "gender": "Female",
        "sample_text": "Good day! I am Victoria. I provide a sophisticated and professional British voice experience.",
    },
    {
        "id": "Google.en-US-Chirp3-HD-Kore",
        "name": "Chloe (Chirp3 Ultra-HD Female - Soft & Friendly)",
        "accent": "US English",
        "gender": "Female",
        "sample_text": "Hello! I am Chloe. I offer a gentle, friendly, and reassuring conversational tone.",
    },
    # Male Voices
    {
        "id": "Google.en-US-Chirp3-HD-Fenrir",
        "name": "Alex (Chirp3 Ultra-HD Male - US)",
        "accent": "US English",
        "gender": "Male",
        "sample_text": "Hello! This is Alex. I am ready to handle your outbound customer feedback operations.",
    },
    {
        "id": "Google.en-US-Journey-D",
        "name": "Marcus (Journey Deep Male - US)",
        "accent": "US English",
        "gender": "Male",
        "sample_text": "Greetings! I am Marcus, your AI customer operations specialist with a deep, authoritative voice.",
    },
    {
        "id": "Google.en-IN-Wavenet-B",
        "name": "Rohan (Wavenet Neural Male - India)",
        "accent": "Indian English",
        "gender": "Male",
        "sample_text": "Hello! I am Rohan. I bring a clear, polite, and professional Indian male voice persona.",
    },
    {
        "id": "Google.en-GB-Studio-C",
        "name": "Oliver (Studio Premium Male - UK British)",
        "accent": "British English",
        "gender": "Male",
        "sample_text": "Hello there! I am Oliver, offering a crisp, refined British male voice for your survey calls.",
    },
    {
        "id": "Google.en-US-Chirp3-HD-Puck",
        "name": "Ethan (Chirp3 Ultra-HD Male - Dynamic)",
        "accent": "US English",
        "gender": "Male",
        "sample_text": "Hey there! I am Ethan, your energetic and engaging voice AI assistant.",
    },
]

ACTIVE_VOICE = "Google.en-IN-Wavenet-B"


def get_active_agent_info() -> Dict[str, Any]:
    """Retrieves active voice catalog record and agent name."""
    global ACTIVE_VOICE
    v_info = next((v for v in VOICE_CATALOG if v["id"] == ACTIVE_VOICE), VOICE_CATALOG[0])
    return {
        "voice_id": ACTIVE_VOICE,
        "agent_name": v_info["name"].split(" ")[0],
        "info": v_info,
    }


def get_active_voice() -> str:
    """Returns active voice identifier string."""
    return ACTIVE_VOICE


def get_active_agent_name() -> str:
    """Returns active agent display name."""
    return get_active_agent_info()["agent_name"]


# =========================
# DYNAMIC TUNNEL MANAGEMENT
# =========================
active_tunnel_url = ""


def is_public_host(host: str) -> bool:
    """Checks if a hostname/host string is a public address and not local/LAN."""
    if not host:
        return False
    clean = host.strip().lower()
    if clean.startswith("http://") or clean.startswith("https://"):
        clean = urllib.parse.urlparse(clean).netloc
    clean_host = clean.split(":")[0]
    if clean_host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or clean_host.endswith(".local"):
        return False
    if clean_host.startswith("192.168.") or clean_host.startswith("10."):
        return False
    if clean_host.startswith("172."):
        parts = clean_host.split(".")
        if len(parts) >= 2 and parts[1].isdigit() and 16 <= int(parts[1]) <= 31:
            return False
    return True


def get_base_url() -> str:
    """Returns live public HTTPS URL from cloud env, active tunnel, BASE_URL, or request host."""
    r_host = os.getenv("RENDER_EXTERNAL_HOSTNAME")
    if r_host:
        r_host = r_host.rstrip("/")
        return f"https://{r_host}" if not r_host.startswith("http") else r_host

    v_url = os.getenv("VERCEL_URL")
    if v_url:
        v_url = v_url.rstrip("/")
        return f"https://{v_url}" if not v_url.startswith("http") else v_url

    if active_tunnel_url:
        return active_tunnel_url

    base_env = os.getenv("BASE_URL", "").strip().rstrip("/")
    if base_env and is_public_host(base_env):
        return base_env

    try:
        if request and request.host:
            host = request.host.rstrip("/")
            if is_public_host(host):
                return host if host.startswith("http") else f"https://{host}"
    except Exception:
        pass

    if base_env:
        return base_env

    try:
        if request and request.host:
            return f"http://{request.host.rstrip('/')}"
    except Exception:
        pass

    return "http://127.0.0.1:5000"


def update_env_base_url(live_url: str) -> None:
    """Auto-updates BASE_URL key in local .env file and environment."""
    if not live_url:
        return
    os.environ["BASE_URL"] = live_url
    if IS_CLOUD_PROD:
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


def kill_zombie_cloudflared() -> None:
    """Terminates lingering cloudflared processes on Windows."""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "cloudflared.exe"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


def _drain_process_stdout(proc: subprocess.Popen) -> None:
    """Reads stdout continuously in background to prevent buffer fill deadlock."""
    try:
        while proc.poll() is None and proc.stdout:
            line = proc.stdout.readline()
            if not line:
                break
    except Exception:
        pass


def start_ssh_tunnel() -> Optional[str]:
    """Tries SSH-based tunnel providers (serveo.net -> localhost.run)."""
    global active_tunnel_url
    if IS_CLOUD_PROD:
        return None

    try:
        subprocess.run(["ssh", "-V"], capture_output=True, text=True, timeout=5, check=True)
    except Exception:
        return None

    providers = [
        {
            "name": "localhost.run",
            "cmd": [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "ServerAliveInterval=30",
                "-o",
                "ConnectTimeout=15",
                "-R",
                "80:127.0.0.1:5000",
                "nokey@localhost.run",
            ],
            "pattern": r"https://[a-zA-Z0-9.-]+\.lhr\.life",
            "keyword": "lhr.life",
        },
        {
            "name": "serveo.net",
            "cmd": [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "ServerAliveInterval=30",
                "-o",
                "ConnectTimeout=15",
                "-R",
                "80:127.0.0.1:5000",
                "serveo.net",
            ],
            "pattern": r"https://[a-zA-Z0-9.-]+\.serveo\.net",
            "keyword": "serveo.net",
        },
    ]

    for provider in providers:
        try:
            proc = subprocess.Popen(
                provider["cmd"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )
            start_t = time.time()
            found_url = None
            while time.time() - start_t < 20:
                line = proc.stdout.readline()
                if not line:
                    break
                if provider["keyword"] in line:
                    match = re.search(provider["pattern"], line)
                    if match:
                        found_url = match.group(0)
                        active_tunnel_url = found_url
                        print(f"[{provider['name'].upper()} TUNNEL SUCCESS] {found_url}")
                        update_env_base_url(found_url)
                        threading.Thread(target=_drain_process_stdout, args=(proc,), daemon=True).start()
                        return found_url
            if not found_url:
                try:
                    proc.kill()
                except Exception:
                    pass
        except Exception as err:
            print(f"[Auto-Tunnel {provider['name']} Error] {err}")

    return None


def start_local_cloudflare_tunnel() -> Optional[str]:
    """Launches local Cloudflare Free Tunnel via cloudflared.exe."""
    global active_tunnel_url
    if IS_CLOUD_PROD:
        return None

    cf_bin = os.path.join(os.path.dirname(__file__), "cloudflared.exe")
    if not os.path.exists(cf_bin):
        return None

    kill_zombie_cloudflared()
    time.sleep(1)

    try:
        proc = subprocess.Popen(
            [cf_bin, "tunnel", "--url", "http://127.0.0.1:5000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        start_t = time.time()
        found_url = None
        while time.time() - start_t < 20:
            line = proc.stdout.readline()
            if not line:
                break
            if any(err in line for err in ["429", "Too Many Requests", "error code: 1015"]):
                try:
                    proc.kill()
                except Exception:
                    pass
                return None
            if "trycloudflare.com" in line:
                match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                if match:
                    found_url = match.group(0)
                    active_tunnel_url = found_url
                    print(f"[CLOUDFLARE TUNNEL SUCCESS] {found_url}")
                    update_env_base_url(found_url)
                    threading.Thread(target=_drain_process_stdout, args=(proc,), daemon=True).start()
                    return found_url
    except Exception as err:
        print(f"[Auto-Tunnel Error] {err}")

    return None


def start_localtunnel() -> Optional[str]:
    """Launches localtunnel via npx as an instant reliable fallback."""
    global active_tunnel_url
    if IS_CLOUD_PROD:
        return None

    try:
        proc = subprocess.Popen(
            ["npx", "-y", "localtunnel", "--port", "5000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=True,
            bufsize=1,
        )
        start_t = time.time()
        found_url = None
        while time.time() - start_t < 15:
            line = proc.stdout.readline()
            if not line:
                break
            if "loca.lt" in line:
                match = re.search(r"https://[a-zA-Z0-9-]+\.loca\.lt", line)
                if match:
                    found_url = match.group(0)
                    active_tunnel_url = found_url
                    print(f"[LOCALTUNNEL SUCCESS] {found_url}")
                    update_env_base_url(found_url)
                    threading.Thread(target=_drain_process_stdout, args=(proc,), daemon=True).start()
                    return found_url
        if not found_url:
            try:
                proc.kill()
            except Exception:
                pass
    except Exception as err:
        print(f"[Localtunnel Error] {err}")

    return None


def ensure_tunnel() -> str:
    """Master auto-tunnel initializer: Cloudflare -> localtunnel -> SSH -> BASE_URL fallback."""
    global active_tunnel_url
    if IS_CLOUD_PROD:
        return os.getenv("BASE_URL", "")

    if active_tunnel_url:
        return active_tunnel_url

    cf_url = start_local_cloudflare_tunnel()
    if cf_url:
        return cf_url

    lt_url = start_localtunnel()
    if lt_url:
        return lt_url

    ssh_url = start_ssh_tunnel()
    if ssh_url:
        return ssh_url

    fallback = os.getenv("BASE_URL", "").strip().rstrip("/")
    active_tunnel_url = fallback
    return fallback


# Start tunnel asynchronously on local dev to prevent blocking Flask server boot
if not IS_CLOUD_PROD and (os.environ.get("WERKZEUG_RUN_MAIN") == "true" or os.environ.get("FLASK_ENV") != "development"):
    threading.Thread(target=ensure_tunnel, daemon=True).start()



# =========================
# DATA STORAGE & HELPERS
# =========================
def get_initial_seed_data() -> List[Dict[str, Any]]:
    """Returns initial seed customer records."""
    return [
        {
            "id": "c101",
            "name": "Vikas Kumar",
            "phone": "+919057262630",
            "status": "completed",
            "feedback": [
                "The service was wonderful! Quick delivery and friendly staff.",
                "I would rate it 5 stars.",
            ],
            "rating": 5,
            "sentiment": "Positive",
            "transcript": [
                {
                    "speaker": "ai",
                    "text": "Hello! This is Sarah calling from Feedback Ops. How was your experience with our service?",
                },
                {
                    "speaker": "customer",
                    "text": "The service was wonderful! Quick delivery and friendly staff.",
                },
                {
                    "speaker": "ai",
                    "text": "That is so great to hear! How many stars out of 5 would you give us?",
                },
                {"speaker": "customer", "text": "I would rate it 5 stars."},
                {
                    "speaker": "ai",
                    "text": "Thank you so much for your feedback! Have a lovely day. Goodbye.",
                },
            ],
            "created_at": time.strftime("%Y-%m-%d %H:%M"),
            "last_call": "10:17 AM",
        }
    ]


DB_FILE_PATH = os.path.join("/tmp" if IS_VERCEL else os.path.dirname(__file__), "customers_store.json")


def load_customers_from_disk() -> List[Dict[str, Any]]:
    """Loads customer dataset from JSON storage file or seed fallback."""
    if os.path.exists(DB_FILE_PATH):
        try:
            with open(DB_FILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception as e:
            print(f"[Storage Load Error] {e}")
    return get_initial_seed_data()


def save_customers_to_disk() -> None:
    """Saves active customer dataset to JSON storage file."""
    try:
        with open(DB_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(customers, f, indent=2)
    except Exception as e:
        print(f"[Storage Save Error] {e}")


customers: List[Dict[str, Any]] = load_customers_from_disk()


def normalize_phone_number(phone: Any) -> str:
    """Normalizes phone numbers to standard E.164 format (+91XXXXXXXXXX)."""
    if not phone:
        return ""
    cleaned = re.sub(r"[^\d+]", "", str(phone).strip())
    if not cleaned:
        return ""
    if cleaned.startswith("+"):
        return cleaned
    if cleaned.startswith("00"):
        return "+" + cleaned[2:]
    if cleaned.startswith("0") and len(cleaned) == 11:
        cleaned = cleaned[1:]
    if len(cleaned) == 10:
        return f"+91{cleaned}"
    if len(cleaned) == 12 and cleaned.startswith("91"):
        return f"+{cleaned}"
    return f"+{cleaned}"


def find_customer(
    customer_id: Optional[str] = None, phone: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Searches customer records by ID or phone number."""
    if customer_id:
        c = next((item for item in customers if item["id"] == customer_id), None)
        if c:
            return c
    if phone:
        norm_phone = normalize_phone_number(phone)
        clean_target = re.sub(r"\D", "", str(phone))
        for item in customers:
            item_phone = item.get("phone", "")
            if item_phone == norm_phone:
                return item
            clean_item = re.sub(r"\D", "", str(item_phone))
            if clean_item and (clean_item.endswith(clean_target) or clean_target.endswith(clean_item)):
                return item
    return None


def generate_ai_response(customer_text: str, customer: Optional[Dict[str, Any]] = None) -> str:
    """Generates conversational AI response via Gemini API with smart fallback."""
    ai_text = ""
    lower = customer_text.lower()
    agent_name = get_active_agent_name()

    if gemini:
        try:
            prompt = (
                f"You are {agent_name} calling from BCT Fibernet regarding internet service feedback.\n"
                f'The customer said: "{customer_text}"\n\n'
                "Rules:\n"
                "1. Acknowledge their feedback about BCT Fibernet internet service naturally.\n"
                "2. If they haven't given a 1 to 5 star rating yet, ask for a star rating out of 5.\n"
                "3. Keep your reply super concise (maximum 15 words).\n"
                "4. Speak naturally without markdown or internal labels."
            )
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
# WEB ROUTES & ENDPOINTS
# =========================
@app.route("/")
def index():
    """Serves main dashboard SPA."""
    return render_template("index.html")



@app.route("/api/health")
def health():
    """Returns application health and environment info."""
    env_name = "Render Production" if IS_RENDER else ("Vercel Production" if IS_VERCEL else "Local Development")
    return jsonify({
        "status": "ok",
        "engine": "Gemini 2.5 Flash + Twilio Voice",
        "active_voice": get_active_voice(),
        "environment": env_name,
        "base_url": get_base_url(),
    })



@app.route("/api/voices", methods=["GET", "POST"])
def manage_voices():
    """Fetches catalog or updates active AI voice."""
    global ACTIVE_VOICE
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        voice_id = data.get("voice_id")
        found = next((v for v in VOICE_CATALOG if v["id"] == voice_id), None)
        if not found:
            return jsonify({"success": False, "error": f"Voice ID '{voice_id}' not found in catalog"}), 400
        ACTIVE_VOICE = voice_id
        return jsonify({"success": True, "active_voice": ACTIVE_VOICE, "voice_info": found})

    return jsonify({"success": True, "active_voice": ACTIVE_VOICE, "voices": VOICE_CATALOG})



@app.route("/api/demo-audio", methods=["GET"])
def stream_voice_demo():
    """Streams sample audio voice preview."""
    voice_id = request.args.get("voice_id") or get_active_voice()
    v_info = next((v for v in VOICE_CATALOG if v["id"] == voice_id), VOICE_CATALOG[0])
    text = v_info.get("sample_text", "Hello! I am your AI Voice Assistant.")
    lang = "hi" if "IN" in voice_id and "Priya" in v_info["name"] else ("en-uk" if "GB" in voice_id else "en")

    tts_url = f"https://translate.google.com/translate_tts?ie=UTF-8&tl={lang}&client=tw-ob&q={urllib.parse.quote(text)}"
    try:
        req = urllib.request.Request(tts_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return Response(resp.read(), mimetype="audio/mpeg")
    except Exception as e:
        print(f"[Demo Audio Stream Error] {e}")
        return jsonify({"error": "Failed to stream audio"}), 500



@app.route("/api/customers", methods=["GET", "POST"])
def handle_customers():
    """Lists all customers or creates a new customer task."""
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        name = str(data.get("name", "")).strip()
        raw_phone = str(data.get("phone", "")).strip()

        if not name or not raw_phone:
            return jsonify({"success": False, "error": "Name and phone number are required"}), 400

        phone = normalize_phone_number(raw_phone)
        existing = find_customer(phone=phone)
        if existing:
            return jsonify({"success": False, "error": f"Customer with phone {phone} already exists ({existing['name']})"}), 400

        customer = {
            "id": f"c{int(time.time() % 100000)}",
            "name": name,
            "phone": phone,
            "status": "pending",
            "feedback": [],
            "rating": None,
            "sentiment": "Neutral",
            "transcript": [],
            "created_at": time.strftime("%Y-%m-%d %H:%M"),
            "last_call": None,
        }
        customers.append(customer)
        save_customers_to_disk()
        return jsonify({"success": True, "customer": customer}), 201

    customers = load_customers_from_disk()
    return jsonify(customers)



@app.route("/api/customers/<customer_id>", methods=["GET", "DELETE"])
def handle_customer_by_id(customer_id):
    """Retrieves or deletes a single customer record."""
    global customers
    c = find_customer(customer_id=customer_id)
    if not c:
        return jsonify({"success": False, "error": "Customer not found"}), 404

    if request.method == "DELETE":
        customers = [item for item in customers if item["id"] != customer_id]
        save_customers_to_disk()
        return jsonify({"success": True, "message": "Customer deleted successfully"})

    return jsonify({"success": True, "customer": c})



@app.route("/api/customers/<customer_id>/feedback", methods=["DELETE"])
def delete_customer_feedback(customer_id):
    """Clears feedback history for a specific customer."""
    c = find_customer(customer_id=customer_id)
    if not c:
        return jsonify({"success": False, "error": "Customer not found"}), 404
    c.update({"feedback": [], "rating": None, "sentiment": "Neutral", "transcript": []})
    if c.get("status") == "completed":
        c["status"] = "pending"
    save_customers_to_disk()
    return jsonify({"success": True, "message": "Customer feedback cleared successfully", "customer": c})


@app.route("/api/seed", methods=["POST"])
def reset_seed_data():
    """Resets customer store back to initial sample dataset."""
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
                {"speaker": "ai", "text": "Thank you so much for your feedback! Have a lovely day. Goodbye."},
            ],
            "created_at": time.strftime("%Y-%m-%d %H:%M"),
            "last_call": "Recent",
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
            "last_call": None,
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
            "last_call": None,
        },
    ])
    save_customers_to_disk()
    return jsonify({"success": True, "message": "Sample data reset successfully", "customers": customers})



# =========================
# CALL CONTROL & TWILIO API
# =========================
@app.route("/api/call", methods=["POST"])
def make_call():
    """Triggers outbound AI voice feedback call."""
    data = request.get_json(force=True, silent=True) or {}
    customer_id = data.get("customer_id")
    phone = data.get("phone")

    customer = find_customer(customer_id=customer_id, phone=phone)
    if customer_id and not customer:
        return jsonify({"success": False, "error": "Customer ID not found"}), 404

    raw_target = customer["phone"] if customer else phone
    target_phone = normalize_phone_number(raw_target)
    if not target_phone:
        return jsonify({"success": False, "error": "Phone number or valid customer_id is required"}), 400

    if customer:
        customer["phone"] = target_phone

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
            "message": f"Twilio client not initialized with real SID/Token, simulated call status for {target_phone}.",
        })

    try:
        call = twilio.calls.create(
            to=target_phone,
            from_=TWILIO_PHONE_NUMBER,
            url=voice_url,
            method="POST",
            status_callback=status_url,
            status_callback_method="POST",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
        )

        if customer:
            customer["status"] = "calling"
            customer["call_sid"] = call.sid
            customer["last_call"] = time.strftime("%H:%M:%S")

        return jsonify({
            "success": True,
            "call_id": call.sid,
            "status": call.status,
            "message": f"AI call initiated to {customer['name'] if customer else target_phone}",
        })
    except Exception as e:
        print(f"[Call Exception] {e}")
        if customer:
            customer["status"] = "failed"
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/twilio/voice", methods=["POST", "GET"])
def twilio_voice():
    """Initial TwiML entry point when call connects."""
    customer_id = request.args.get("customer_id")
    phone = request.args.get("phone") or request.form.get("To") or request.form.get("From")
    customer = find_customer(customer_id=customer_id, phone=phone)

    if customer:
        customer["status"] = "calling"
        save_customers_to_disk()

    base = get_base_url()
    cid_param = f"?customer_id={customer['id']}" if customer else ""
    feedback_url = f"{base}/api/twilio/feedback{cid_param}"

    response = VoiceResponse()
    agent_name = get_active_agent_name()
    c_name = customer["name"] if customer else ""
    greeting_text = (
        f"Hello {c_name}! I am {agent_name} from BCT Fibernet, calling for quick feedback on your internet service. "
        "How is your experience?"
    )

    v = get_active_voice()
    response.say(greeting_text, voice=v)

    if customer:
        customer["transcript"] = [{"speaker": "ai", "text": greeting_text}]
        save_customers_to_disk()

    gather = response.gather(
        input="speech",
        action=feedback_url,
        method="POST",
        speech_timeout="auto",
        language="en-IN",
    )
    gather.say("How is your internet service experience?", voice=v)

    response.say("Thank you for your feedback! Goodbye.", voice=v)
    response.hangup()

    return Response(str(response), status=200, content_type="text/xml")


@app.route("/api/twilio/feedback", methods=["POST"])
def twilio_feedback():
    """Processes customer speech result and renders conversational response."""
    customer_id = request.args.get("customer_id")
    called_phone = request.form.get("To") or request.form.get("From")
    customer_text = request.form.get("SpeechResult", "").strip()
    customer = find_customer(customer_id=customer_id, phone=called_phone)

    response = VoiceResponse()
    base = get_base_url()
    cid_param = f"?customer_id={customer['id']}" if customer else ""
    feedback_url = f"{base}/api/twilio/feedback{cid_param}"
    v = get_active_voice()

    if not customer_text:
        response.say("I didn't quite catch that. Could you please tell me about your experience?", voice=v)
        gather = response.gather(
            input="speech",
            action=feedback_url,
            method="POST",
            speech_timeout="auto",
            language="en-IN",
        )
        gather.say("I am listening.", voice=v)
        return Response(str(response), status=200, content_type="text/xml")

    if customer:
        customer.setdefault("feedback", []).append(customer_text)
        customer.setdefault("transcript", []).append({"speaker": "customer", "text": customer_text})

        if customer.get("rating") is None:
            nums = re.findall(r"\b([1-5])\b", customer_text)
            if nums:
                customer["rating"] = int(nums[0])

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
    if customer:
        customer.setdefault("transcript", []).append({"speaker": "ai", "text": ai_text})

    bye_keywords = ["bye", "goodbye", "thank you", "thanks", "that's all", "done", "no", "that is all"]
    is_closing = any(w in customer_text.lower() for w in bye_keywords)

    response.say(ai_text, voice=v)

    if is_closing or (customer and customer.get("rating") is not None and len(customer.get("feedback", [])) >= 2):
        response.say("Have a fantastic day! Goodbye.", voice=v)
        response.hangup()
        if customer:
            customer["status"] = "completed"
    else:
        gather = response.gather(
            input="speech",
            action=feedback_url,
            method="POST",
            speech_timeout="auto",
            language="en-IN",
        )
        gather.say("Is there anything else you would like to add?", voice=v)
        response.say("Thank you for your feedback! Goodbye.", voice=v)
        response.hangup()

    if customer:
        save_customers_to_disk()

    return Response(str(response), status=200, content_type="text/xml")


@app.route("/api/twilio/status", methods=["POST"])
def twilio_status():
    """Webhook for Twilio call state transitions."""
    customer_id = request.args.get("customer_id")
    call_status = request.form.get("CallStatus", "")
    phone = request.form.get("To", "") or request.form.get("From", "")

    customer = find_customer(customer_id=customer_id, phone=phone)
    if customer:
        if call_status == "completed":
            customer["status"] = "completed"
        elif call_status in ("failed", "busy", "no-answer", "canceled"):
            customer["status"] = "failed"
        elif call_status in ("initiated", "ringing", "in-progress"):
            customer["status"] = "calling"
        save_customers_to_disk()

    return Response("OK", status=200)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
