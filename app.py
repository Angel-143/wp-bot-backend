"""
WhatsApp Automation Backend
Flask + Twilio WhatsApp API
Run: pip install flask flask-cors twilio && python app.py
"""

from flask import Flask, request, jsonify
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
# Demo data seed (runs once if leads.json doesn't exist)
# ─────────────────────────────────────────────────────────────────────────────

def seed_demo():
    if os.path.exists(LEADS_FILE):
        return
    demo = [
        {
            "id": str(uuid.uuid4()), "name": "Priya Sharma",
            "phone": "+919876543210", "last_message": "What are the fees?",
            "status": "contacted", "created_at": "2025-04-08T10:30:00",
            "updated_at": "2025-04-08T10:35:00",
            "messages": [
                {"text": "hi",                    "time": "2025-04-08T10:30:00", "direction": "inbound"},
                {"text": "Welcome! Tell me your name.", "time": "2025-04-08T10:30:05", "direction": "outbound"},
                {"text": "Priya Sharma",           "time": "2025-04-08T10:31:00", "direction": "inbound"},
                {"text": "Nice to meet you, Priya! 👋", "time": "2025-04-08T10:31:05", "direction": "outbound"},
                {"text": "What are the fees?",     "time": "2025-04-08T10:32:00", "direction": "inbound"},
                {"text": "💰 Fee Structure: Foundation ₹15k, Standard ₹25k, Premium ₹40k/year", "time": "2025-04-08T10:32:05", "direction": "outbound"},
            ]
        },
        {
            "id": str(uuid.uuid4()), "name": "Rahul Verma",
            "phone": "+919123456789", "last_message": "hostel",
            "status": "new", "created_at": "2025-04-09T14:20:00",
            "updated_at": "2025-04-09T14:25:00",
            "messages": [
                {"text": "hostel", "time": "2025-04-09T14:20:00", "direction": "inbound"},
                {"text": "🏠 Boys Hostel ₹8k/mo · Girls ₹8.5k/mo · WiFi, AC, Mess, Gym", "time": "2025-04-09T14:20:05", "direction": "outbound"},
            ]
        },
        {
            "id": str(uuid.uuid4()), "name": "Anjali Singh",
            "phone": "+918765432109", "last_message": "What is the admission process?",
            "status": "closed", "created_at": "2025-04-07T09:15:00",
            "updated_at": "2025-04-07T09:20:00",
            "messages": [
                {"text": "What is the admission process?", "time": "2025-04-07T09:15:00", "direction": "inbound"},
                {"text": "🙏 Our team will contact you shortly. ✅", "time": "2025-04-07T09:15:05", "direction": "outbound"},
            ]
        },
        {
            "id": str(uuid.uuid4()), "name": "Arjun Patel",
            "phone": "+917654321098", "last_message": "fees",
            "status": "new", "created_at": "2025-04-10T08:05:00",
            "updated_at": "2025-04-10T08:05:00",
            "messages": [
                {"text": "fees", "time": "2025-04-10T08:05:00", "direction": "inbound"},
                {"text": "💰 Standard ₹25k/year includes material & doubt sessions.", "time": "2025-04-10T08:05:05", "direction": "outbound"},
            ]
        },
    ]
    save_leads(demo)
    print("✅ Demo leads seeded.")


if __name__ == "__main__":
    seed_demo()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
