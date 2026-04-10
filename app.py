"""
WhatsApp Automation Backend
Flask + Twilio WhatsApp API
Run: pip install flask flask-cors twilio && python app.py
"""

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import json, os, uuid
from datetime import datetime

# ── Try to import Twilio (optional – graceful fallback for demo) ──────────────
try:
    from twilio.twiml.messaging_response import MessagingResponse
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    print("⚠️  Twilio not installed. Webhook will return plain text. Install: pip install twilio")

app = Flask(__name__)
CORS(app)  # Allow frontend (localhost / file://) to connect

LEADS_FILE = os.path.join(os.path.dirname(__file__), "leads.json")

# ─────────────────────────────────────────────────────────────────────────────
# JSON helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_leads():
    if not os.path.exists(LEADS_FILE):
        return []
    with open(LEADS_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_leads(leads):
    with open(LEADS_FILE, "w") as f:
        json.dump(leads, f, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Root route  –  Beautiful status page
# ─────────────────────────────────────────────────────────────────────────────

STATUS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>WA Bot — Server Status</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@400;500&display=swap" rel="stylesheet"/>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:'DM Sans',sans-serif;background:#0d0d0d;color:#fff;min-height:100vh;display:flex;align-items:center;justify-content:center}
  .card{background:#141414;border:1px solid #222;border-radius:24px;padding:48px 52px;max-width:520px;width:90%;text-align:center;box-shadow:0 32px 80px rgba(0,0,0,.5)}
  .icon{font-size:52px;margin-bottom:20px;animation:float 3s ease-in-out infinite}
  @keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}
  h1{font-family:'Syne',sans-serif;font-size:32px;font-weight:800;letter-spacing:-.5px;margin-bottom:6px}
  h1 span{background:linear-gradient(135deg,#ff4d8d,#ff8c42);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
  .subtitle{color:#666;font-size:15px;margin-bottom:36px}
  .status-row{display:flex;align-items:center;justify-content:space-between;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:12px;padding:14px 18px;margin-bottom:10px;text-align:left}
  .status-label{font-size:13px;color:#888}
  .status-val{font-size:13px;font-weight:500}
  .badge{display:inline-flex;align-items:center;gap:6px;background:rgba(52,211,153,.12);color:#34d399;padding:4px 10px;border-radius:99px;font-size:12px;font-weight:600}
  .dot{width:7px;height:7px;border-radius:50%;background:#34d399;animation:pulse 2s infinite}
  @keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(52,211,153,.4)}50%{box-shadow:0 0 0 5px rgba(52,211,153,0)}}
  .endpoints{margin-top:28px;text-align:left}
  .ep-title{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#555;margin-bottom:12px;font-weight:600}
  .ep{display:flex;align-items:center;gap:10px;padding:10px 14px;background:#1a1a1a;border-radius:8px;margin-bottom:6px}
  .method{font-size:10px;font-weight:700;padding:3px 7px;border-radius:5px;letter-spacing:.04em}
  .get{background:rgba(56,189,248,.15);color:#38bdf8}
  .post{background:rgba(250,204,21,.15);color:#facc15}
  .ep-path{font-family:monospace;font-size:13px;color:#ccc}
  .ep-desc{margin-left:auto;font-size:11px;color:#555}
  .footer{margin-top:28px;font-size:12px;color:#444}
  .footer a{color:#ff4d8d;text-decoration:none}
</style>
</head>
<body>
<div class="card">
  <div class="icon">🤖</div>
  <h1>WA<span>Auto</span> Bot</h1>
  <p class="subtitle">WhatsApp Automation Backend</p>

  <div class="status-row">
    <span class="status-label">Server Status</span>
    <span class="badge"><span class="dot"></span> Online & Running</span>
  </div>
  <div class="status-row">
    <span class="status-label">Total Leads</span>
    <span class="status-val">{{ total_leads }}</span>
  </div>
  <div class="status-row">
    <span class="status-label">Twilio</span>
    <span class="status-val" style="color:{{ twilio_color }}">{{ twilio_status }}</span>
  </div>
  <div class="status-row">
    <span class="status-label">Server Time</span>
    <span class="status-val">{{ server_time }}</span>
  </div>

  <div class="endpoints">
    <div class="ep-title">Available Endpoints</div>
    <div class="ep"><span class="method post">POST</span><span class="ep-path">/webhook</span><span class="ep-desc">Twilio incoming</span></div>
    <div class="ep"><span class="method get">GET</span><span class="ep-path">/leads</span><span class="ep-desc">All leads</span></div>
    <div class="ep"><span class="method post">POST</span><span class="ep-path">/leads</span><span class="ep-desc">Add lead</span></div>
    <div class="ep"><span class="method get">GET</span><span class="ep-path">/stats</span><span class="ep-desc">Dashboard stats</span></div>
    <div class="ep"><span class="method get">GET</span><span class="ep-path">/health</span><span class="ep-desc">Health check</span></div>
  </div>

  <div class="footer">Built with Flask + Twilio &nbsp;·&nbsp; <a href="/health">/health</a> &nbsp;·&nbsp; <a href="/stats">/stats</a></div>
</div>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def index():
    leads  = load_leads()
    return render_template_string(
        STATUS_HTML,
        total_leads   = len(leads),
        twilio_status = "✅ Available" if TWILIO_AVAILABLE else "⚠️ Not installed",
        twilio_color  = "#34d399" if TWILIO_AVAILABLE else "#facc15",
        server_time   = datetime.now().strftime("%d %b %Y, %H:%M:%S UTC"),
    )


@app.route("/health", methods=["GET"])
def health():
    leads = load_leads()
    return jsonify({
        "status":        "ok",
        "server":        "WA Auto Bot",
        "total_leads":   len(leads),
        "twilio":        TWILIO_AVAILABLE,
        "timestamp":     datetime.now().isoformat(),
    })

# ─────────────────────────────────────────────────────────────────────────────
# Session store: tracks conversation state per phone number
# ─────────────────────────────────────────────────────────────────────────────
sessions = {}

def get_auto_reply(phone, message_body):
    """Return (reply_text, lead_update_dict)."""
    msg     = message_body.strip().lower()
    session = sessions.get(phone, {})
    reply, lead_update = "", {}

    # Awaiting name (multi-turn)
    if session.get("awaiting_name"):
        name = message_body.strip().title()
        sessions[phone] = {"name": name}
        reply = (
            f"Nice to meet you, {name}! 👋\n\n"
            "How can I help you today?\n"
            "• Type *fees* for pricing info\n"
            "• Type *hostel* for hostel details\n"
            "• Or just ask your question!"
        )
        lead_update = {"name": name}
        return reply, lead_update

    # Greeting
    if msg in ("hi", "hello", "hey", "hii", "helo", "namaste"):
        sessions[phone] = {"awaiting_name": True}
        reply = (
            "👋 Welcome! I'm your virtual assistant.\n\n"
            "Could you please tell me your *name*? 😊"
        )

    # Fees
    elif any(k in msg for k in ("fee", "price", "cost", "charges", "amount")):
        reply = (
            "💰 *Fee Structure*\n\n"
            "• Foundation Course: ₹15,000/year\n"
            "• Standard Course: ₹25,000/year\n"
            "• Premium Course: ₹40,000/year\n\n"
            "All plans include study material & doubt sessions.\n"
            "Reply *hostel* for accommodation info."
        )

    # Hostel
    elif any(k in msg for k in ("hostel", "accommodation", "room", "stay", "pg")):
        reply = (
            "🏠 *Hostel Information*\n\n"
            "• Boys Hostel: ₹8,000/month\n"
            "• Girls Hostel: ₹8,500/month\n"
            "• Facilities: WiFi, AC rooms, Mess, Gym\n"
            "• Availability: Limited seats\n\n"
            "Contact us at +91-XXXXXXXXXX to book."
        )

    # Unknown
    else:
        name     = session.get("name", "")
        greeting = f"Thanks {name}! " if name else ""
        reply    = (
            f"🙏 {greeting}We received your message.\n\n"
            "Our team will contact you shortly. ✅\n"
            "You can also ask about *fees* or *hostel*."
        )

    return reply, lead_update


# ─────────────────────────────────────────────────────────────────────────────
# Webhook  –  Twilio sends POST here for every incoming WhatsApp message
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    from_number  = request.values.get("From", "")          # "whatsapp:+91XXXXXXXXXX"
    phone        = from_number.replace("whatsapp:", "")

    reply_text, lead_update = get_auto_reply(phone, incoming_msg)

    # ── Upsert lead ──────────────────────────────────────────────────────────
    leads    = load_leads()
    existing = next((l for l in leads if l["phone"] == phone), None)

    now = datetime.now().isoformat()
    if existing:
        existing["messages"].append({"text": incoming_msg, "time": now, "direction": "inbound"})
        existing["messages"].append({"text": reply_text,   "time": now, "direction": "outbound"})
        if lead_update.get("name"):
            existing["name"] = lead_update["name"]
        existing["last_message"] = incoming_msg
        existing["updated_at"]   = now
    else:
        leads.append({
            "id":           str(uuid.uuid4()),
            "name":         lead_update.get("name", "Unknown"),
            "phone":        phone,
            "last_message": incoming_msg,
            "status":       "new",
            "created_at":   now,
            "updated_at":   now,
            "messages":     [
                {"text": incoming_msg, "time": now, "direction": "inbound"},
                {"text": reply_text,   "time": now, "direction": "outbound"},
            ],
        })

    save_leads(leads)

    # ── Return TwiML response ─────────────────────────────────────────────────
    if TWILIO_AVAILABLE:
        resp = MessagingResponse()
        resp.message(reply_text)
        return str(resp), 200, {"Content-Type": "text/xml"}
    else:
        return f"<Response><Message>{reply_text}</Message></Response>", 200, {"Content-Type": "text/xml"}


# ─────────────────────────────────────────────────────────────────────────────
# REST  API  –  Leads
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/leads", methods=["GET"])
def get_leads():
    leads  = load_leads()
    search = request.args.get("search", "").lower()
    status = request.args.get("status", "")

    if search:
        leads = [l for l in leads if
                 search in l.get("name",         "").lower() or
                 search in l.get("phone",        "").lower() or
                 search in l.get("last_message", "").lower()]
    if status:
        leads = [l for l in leads if l.get("status") == status]

    return jsonify({"leads": leads, "total": len(leads)})


@app.route("/leads", methods=["POST"])
def add_lead():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    now     = datetime.now().isoformat()
    message = data.get("message", "Added manually")
    lead    = {
        "id":           str(uuid.uuid4()),
        "name":         data.get("name",   "Unknown"),
        "phone":        data.get("phone",  ""),
        "last_message": message,
        "status":       data.get("status", "new"),
        "created_at":   now,
        "updated_at":   now,
        "messages":     [{"text": message, "time": now, "direction": "inbound"}],
    }
    leads = load_leads()
    leads.append(lead)
    save_leads(leads)
    return jsonify({"message": "Lead added", "lead": lead}), 201


@app.route("/leads/<lead_id>", methods=["PUT"])
def update_lead(lead_id):
    data  = request.get_json()
    leads = load_leads()
    lead  = next((l for l in leads if l["id"] == lead_id), None)
    if not lead:
        return jsonify({"error": "Lead not found"}), 404
    for key in ("name", "status", "phone"):
        if key in data:
            lead[key] = data[key]
    lead["updated_at"] = datetime.now().isoformat()
    save_leads(leads)
    return jsonify({"message": "Lead updated", "lead": lead})


@app.route("/leads/<lead_id>", methods=["DELETE"])
def delete_lead(lead_id):
    leads   = load_leads()
    updated = [l for l in leads if l["id"] != lead_id]
    if len(updated) == len(leads):
        return jsonify({"error": "Lead not found"}), 404
    save_leads(updated)
    return jsonify({"message": "Lead deleted"})


@app.route("/leads/<lead_id>/messages", methods=["GET"])
def get_messages(lead_id):
    leads = load_leads()
    lead  = next((l for l in leads if l["id"] == lead_id), None)
    if not lead:
        return jsonify({"error": "Lead not found"}), 404
    return jsonify({"lead": lead, "messages": lead.get("messages", [])})


# ─────────────────────────────────────────────────────────────────────────────
# REST  API  –  Stats
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/stats", methods=["GET"])
def get_stats():
    leads = load_leads()
    recent = sorted(leads, key=lambda x: x.get("created_at", ""), reverse=True)[:5]
    return jsonify({
        "total":     len(leads),
        "new":       sum(1 for l in leads if l.get("status") == "new"),
        "contacted": sum(1 for l in leads if l.get("status") == "contacted"),
        "closed":    sum(1 for l in leads if l.get("status") == "closed"),
        "recent":    recent,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Ensure leads.json exists on startup (empty, no demo data)
# ─────────────────────────────────────────────────────────────────────────────

def init_storage():
    """Create an empty leads.json if it doesn't exist yet."""
    if not os.path.exists(LEADS_FILE):
        save_leads([])
        print("✅ leads.json initialised (empty).")


if __name__ == "__main__":
    init_storage()
    print("\n🚀  WhatsApp Automation Backend")
    print("────────────────────────────────")
    print("📡  Webhook : POST http://localhost:5000/webhook")
    print("📊  Leads   : GET  http://localhost:5000/leads")
    print("📈  Stats   : GET  http://localhost:5000/stats")
    print("────────────────────────────────\n")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
