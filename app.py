"""
Real-Time AI Customer Feedback Calling Agent
Architecture: Twilio <-> Flask WebSocket <-> Gemini (text) + gTTS (speech)
Since Gemini Live bidi API access is denied for this key, we use:
  - Google Speech Recognition (STT) to transcribe caller audio
  - Gemini text API to generate responses
  - gTTS to convert responses to speech (u-law 8kHz for Twilio)
"""

import os
import io
import json
import base64
import asyncio
import miniaudio
import threading
import queue
import logging
import tempfile
import urllib.request
from time import sleep
from urllib.parse import quote, unquote
from uuid import uuid4

from flask import Flask, request, jsonify, Response, render_template
from flask_sock import Sock
from dotenv import load_dotenv

from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream, Parameter

from google import genai
from google.genai import types as genai_types

import speech_recognition as sr
import miniaudio
from gtts import gTTS

try:
    import audioop
except ImportError:
    import audioop_lts as audioop

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────
load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE       = os.getenv("TWILIO_PHONE_NUMBER", "")
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL       = "gemini-2.5-flash"   # text-only, always works

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

app  = Flask(__name__)
sock = Sock(app)

@app.after_request
def _no_ngrok_warning(r):
    r.headers["ngrok-skip-browser-warning"] = "true"
    return r

twilio_client  = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID else None
gemini_client  = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# ──────────────────────────────────────────────
# IN-MEMORY STATE
# ──────────────────────────────────────────────
customers      = {}
campaign_state = {"running": False}

def get_base_url():
    try:
        data = json.loads(urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=1).read())
        for t in data.get("tunnels", []):
            if t.get("public_url", "").startswith("https://"):
                return t["public_url"].rstrip("/")
    except Exception:
        pass
    return os.getenv("BASE_URL", "").strip().rstrip("/")

# ──────────────────────────────────────────────
# CUSTOMER HELPERS
# ──────────────────────────────────────────────
def make_customer(name, phone, status="pending"):
    return {"id": uuid4().hex[:8], "phone": phone, "name": name,
            "status": status, "rating": None, "feedback": ""}

def find_customer(ident):
    if not ident:
        return None
    ident = str(ident).strip()
    if ident in customers:
        return customers[ident]
    for c in customers.values():
        if c.get("id") == ident or c.get("phone") == ident:
            return c
    return None

# ──────────────────────────────────────────────
# SYSTEM PROMPT
# ──────────────────────────────────────────────
SYSTEM_PROMPT = """You are Sarah, a friendly customer feedback agent for ABC Company.
Your goal: collect a 1-5 star rating and brief feedback from the customer.
Conversation flow:
1. Greet warmly, introduce yourself, ask if they have a moment.
2. Ask for a star rating (1-5).
3. Ask what they liked or how to improve.
4. Thank them and say goodbye.
Rules: short replies (1-2 sentences), friendly, natural, conversational.
If asked anything off-topic, steer back to feedback politely.
Reply ONLY with what you would say aloud – no stage directions, no asterisks."""

# ──────────────────────────────────────────────
# AUDIO HELPERS
# ──────────────────────────────────────────────
SILENCE_THRESHOLD_BYTES = 160 * 50  # ~50 frames of silence before we process

def ulaw_to_pcm16k(ulaw_bytes: bytes) -> bytes:
    """G.711 u-law 8kHz -> 16kHz 16-bit PCM (for speech recognition)."""
    pcm8  = audioop.ulaw2lin(ulaw_bytes, 2)
    pcm16, _ = audioop.ratecv(pcm8, 2, 1, 8000, 16000, None)
    return pcm16

def pcm8_to_ulaw(pcm8: bytes) -> bytes:
    return audioop.lin2ulaw(pcm8, 2)

def text_to_ulaw(text: str) -> bytes:
    """Convert text -> gTTS MP3 -> 8kHz u-law bytes (Twilio-compatible)."""
    try:
        mp3_buf = io.BytesIO()
        gTTS(text=text, lang="en", slow=False).write_to_fp(mp3_buf)
        mp3_bytes = mp3_buf.getvalue()
        # Decode MP3 -> PCM with miniaudio (no ffmpeg needed)
        decoded = miniaudio.decode(mp3_bytes, output_format=miniaudio.SampleFormat.SIGNED16,
                                   nchannels=1, sample_rate=8000)
        pcm_bytes = bytes(decoded.samples)
        return pcm8_to_ulaw(pcm_bytes)
    except Exception as e:
        logging.error("TTS conversion failed: %s", e)
        return b""

def pcm16k_to_wav(pcm: bytes) -> bytes:
    """Wrap raw 16kHz 16-bit PCM in a WAV container for SpeechRecognition."""
    import struct
    ch, sr_, sw = 1, 16000, 2
    data_size   = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, ch, sr_,
        sr_ * ch * sw, ch * sw, sw * 8,
        b"data", data_size
    )
    return header + pcm

def transcribe_pcm(pcm16k: bytes) -> str:
    """Use Google Cloud STT (free tier) to transcribe 16kHz PCM."""
    recognizer = sr.Recognizer()
    wav_data   = pcm16k_to_wav(pcm16k)
    audio_src  = sr.AudioData(wav_data, sample_rate=16000, sample_width=2)
    try:
        return recognizer.recognize_google(audio_src)
    except sr.UnknownValueError:
        return ""
    except Exception as e:
        logging.error("STT error: %s", e)
        return ""

def gemini_reply(history: list, user_text: str) -> str:
    """Get Gemini text response, maintaining conversation history."""
    history.append(genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=user_text)]
    ))
    try:
        resp = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=history,
            config=genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=200,
                temperature=0.7
            )
        )
        reply = resp.text.strip()
    except Exception as e:
        logging.error("Gemini error: %s", e)
        reply = "I'm sorry, I missed that. Could you repeat?"
    history.append(genai_types.Content(
        role="model",
        parts=[genai_types.Part(text=reply)]
    ))
    return reply

# ──────────────────────────────────────────────
# SEND HELPERS
# ──────────────────────────────────────────────
CHUNK_SIZE = 160  # 20ms at 8kHz

def send_tts(ws, stream_sid: str, text: str):
    """Convert text to speech and stream u-law audio to Twilio."""
    logging.info("AI says: %s", text)
    ulaw = text_to_ulaw(text)
    if not ulaw:
        return
    # Send in chunks to avoid buffer overflow
    for i in range(0, len(ulaw), CHUNK_SIZE * 100):
        chunk = ulaw[i : i + CHUNK_SIZE * 100]
        payload = base64.b64encode(chunk).decode("ascii")
        ws.send(json.dumps({
            "event": "media",
            "streamSid": stream_sid,
            "media": {"payload": payload}
        }))

def send_clear(ws, stream_sid: str):
    try:
        ws.send(json.dumps({"event": "clear", "streamSid": stream_sid}))
    except Exception:
        pass

# ──────────────────────────────────────────────
# CALL STATE MACHINE
# ──────────────────────────────────────────────
SILENCE_FRAMES   = 40   # ~1 second of silence = flush audio for STT
AUDIO_FRAME_RATE = 8000
FRAME_SAMPLES    = 160  # 20ms per frame

class CallSession:
    def __init__(self, ws, customer_name: str, customer_phone: str):
        self.ws             = ws
        self.stream_sid     = None
        self.customer_name  = customer_name
        self.customer_phone = customer_phone
        self.history        = []
        self.audio_buf      = bytearray()
        self.silence_count  = 0
        self.speaking       = False
        self.rating         = None
        self.feedback_text  = ""

    def on_start(self, stream_sid: str):
        self.stream_sid = stream_sid
        logging.info("Stream started: %s | %s (%s)", stream_sid, self.customer_name, self.customer_phone)
        greeting = f"Hello! May I speak with {self.customer_name}? This is Sarah calling from ABC Company. Do you have a moment to share your feedback?"
        send_tts(self.ws, stream_sid, greeting)
        self.history.append(genai_types.Content(
            role="model",
            parts=[genai_types.Part(text=greeting)]
        ))

    def on_media(self, ulaw_b64: str):
        ulaw  = base64.b64decode(ulaw_b64)
        level = audioop.rms(audioop.ulaw2lin(ulaw, 2), 2)
        if level > 200:   # active speech
            self.speaking      = True
            self.silence_count = 0
            self.audio_buf    += ulaw
        elif self.speaking:
            self.silence_count += 1
            self.audio_buf     += ulaw
            if self.silence_count >= SILENCE_FRAMES:
                # Caller stopped speaking – process utterance
                self.speaking      = False
                self.silence_count = 0
                buf, self.audio_buf = bytes(self.audio_buf), bytearray()
                threading.Thread(target=self._process_utterance, args=(buf,), daemon=True).start()

    def _process_utterance(self, ulaw_buf: bytes):
        pcm = ulaw_to_pcm16k(ulaw_buf)
        text = transcribe_pcm(pcm)
        if not text:
            logging.info("(no speech detected)")
            return
        logging.info("Customer: %s", text)

        # Simple rating/feedback extraction
        import re
        if self.rating is None:
            nums = re.findall(r"\b([1-5])\b", text)
            if nums:
                self.rating = int(nums[0])
                logging.info("Rating extracted: %d", self.rating)
                c = find_customer(self.customer_phone) or find_customer(self.customer_name)
                if c:
                    c["rating"] = self.rating

        if self.rating and not self.feedback_text and len(text.split()) > 3:
            self.feedback_text = text
            c = find_customer(self.customer_phone) or find_customer(self.customer_name)
            if c:
                c["feedback"] = self.feedback_text
                c["status"]   = "completed"

        reply = gemini_reply(self.history, text)
        send_tts(self.ws, self.stream_sid, reply)

# ──────────────────────────────────────────────
# WEBSOCKET ENDPOINT
# ──────────────────────────────────────────────
@sock.route("/media")
def media_ws(ws):
    logging.info("Twilio WebSocket connected")
    session: CallSession = None

    try:
        while True:
            raw = ws.receive()
            if raw is None:
                break
            try:
                data = json.loads(raw)
            except Exception:
                continue

            event = data.get("event")

            if event == "connected":
                logging.info("Twilio event: connected")

            elif event == "start":
                sd     = data.get("start", {})
                sid    = sd.get("streamSid")
                params = sd.get("customParameters", {})
                name   = unquote(params.get("customer_name", "Customer"))
                phone  = unquote(params.get("phone", ""))
                c = find_customer(phone) or find_customer(name)
                if c:
                    c["status"] = "calling"
                session = CallSession(ws, name, phone)
                session.on_start(sid)

            elif event == "media" and session:
                payload = data.get("media", {}).get("payload", "")
                if payload:
                    session.on_media(payload)

            elif event == "stop":
                logging.info("Twilio event: stop")
                if session:
                    c = find_customer(session.customer_phone) or find_customer(session.customer_name)
                    if c and c["status"] == "calling":
                        c["status"] = "completed" if c.get("rating") else "pending"
                break

    except Exception as e:
        logging.exception("WebSocket error: %s", e)
    finally:
        logging.info("WebSocket closed")

# ──────────────────────────────────────────────
# HTTP ROUTES
# ──────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "model": GEMINI_MODEL})

def _make_call(phone: str, name: str) -> str:
    base = get_base_url()
    url  = f"{base}/twilio/voice?customer_name={quote(name)}&phone={quote(phone)}"
    call = twilio_client.calls.create(to=phone, from_=TWILIO_PHONE, url=url, method="POST")
    logging.info("Call initiated: %s -> %s (%s)", call.sid, name, phone)
    return call.sid

@app.route("/api/call", methods=["POST"])
def api_call():
    data     = request.get_json(silent=True) or {}
    customer = find_customer(data.get("customer_id"))
    phone    = str(data.get("phone") or (customer or {}).get("phone") or "").strip()
    name     = str(data.get("name")  or (customer or {}).get("name")  or "Customer").strip()
    if not phone:
        return jsonify({"success": False, "error": "Phone number required"}), 400
    if not customer:
        customer = make_customer(name, phone, "initiated")
        customers[phone] = customer
    else:
        customer.update({"phone": phone, "name": name, "status": "initiated"})
    try:
        sid = _make_call(phone, name)
        customer.update({"call_sid": sid, "status": "calling"})
        return jsonify({"success": True, "message": f"Calling {name}", "call_sid": sid, "phone": phone})
    except Exception as e:
        logging.exception("Call failed: %s", e)
        customer["status"] = "failed"
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/twilio/voice", methods=["GET", "POST"])
def twilio_voice():
    name  = request.args.get("customer_name", "Customer")
    phone = request.args.get("phone", "")
    base  = get_base_url()
    ws_url = base.replace("https://", "wss://").replace("http://", "ws://")
    resp = VoiceResponse()
    connect = Connect()
    stream  = Stream(url=f"{ws_url}/media")
    stream.append(Parameter(name="customer_name", value=name))
    stream.append(Parameter(name="phone", value=phone))
    connect.append(stream)
    resp.append(connect)
    return Response(str(resp), mimetype="text/xml")

@app.route("/api/customers", methods=["GET", "POST"])
def api_customers():
    if request.method == "GET":
        return jsonify(list(customers.values()))
    data  = request.get_json(silent=True) or {}
    name  = str(data.get("name", "")).strip()
    phone = str(data.get("phone", "")).strip()
    if not name or not phone:
        return jsonify({"success": False, "error": "Name and phone required"}), 400
    if phone in customers:
        return jsonify({"success": False, "error": "Phone already registered"}), 409
    c = make_customer(name, phone)
    customers[phone] = c
    return jsonify({"success": True, "customer": c}), 201

@app.route("/api/campaign", methods=["GET"])
def api_campaign():
    return jsonify({"success": True, "running": campaign_state["running"]})

@app.route("/api/campaign/start", methods=["POST"])
def api_campaign_start():
    campaign_state["running"] = True
    return jsonify({"success": True, "running": True})

@app.route("/api/campaign/stop", methods=["POST"])
def api_campaign_stop():
    campaign_state["running"] = False
    return jsonify({"success": True, "running": False})

# ──────────────────────────────────────────────
# CAMPAIGN WORKER
# ──────────────────────────────────────────────
def _campaign_worker():
    while True:
        try:
            if campaign_state["running"]:
                pending = next((c for c in customers.values() if c.get("status") in ("pending", "queued")), None)
                if pending:
                    pending["status"] = "initiated"
                    try:
                        sid = _make_call(pending["phone"], pending["name"])
                        pending.update({"call_sid": sid, "status": "calling"})
                    except Exception as e:
                        logging.error("Campaign call error: %s", e)
                        pending["status"] = "failed"
                    sleep(20)
                else:
                    sleep(3)
            else:
                sleep(2)
        except Exception as e:
            logging.error("Campaign worker: %s", e)
            sleep(5)

threading.Thread(target=_campaign_worker, daemon=True).start()

# ──────────────────────────────────────────────
# SEED DATA
# ──────────────────────────────────────────────
_s = make_customer("Alex Johnson", "+919057262630")
customers[_s["phone"]] = _s

# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
if __name__ == "__main__":
    base = get_base_url()
    ws   = base.replace("https://", "wss://").replace("http://", "ws://")
    print(f"\n{'='*45}")
    print(" AI Customer Feedback Agent")
    print(f"{'='*45}")
    print(f" Base URL : {base}")
    print(f" WebSocket: {ws}/media")
    print(f" Model    : {GEMINI_MODEL} (text) + gTTS")
    print(f"{'='*45}\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
