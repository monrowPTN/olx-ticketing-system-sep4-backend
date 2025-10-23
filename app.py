# ✅ Load environment variables from .env file (for secrets)
from dotenv import load_dotenv
load_dotenv()

# ✅ Flask core libraries
from flask import Flask, request, jsonify
from flask_cors import CORS
# ✅ Added required imports
import os, re, smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta  # ✅ added timedelta

# ✅ Initialize Flask app BEFORE using CORS
app = Flask(__name__)

CORS(app, resources={
    r"/*": {
        "origins": [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
            "http://tickets.local:3000",
            "http://tickets.local:3001",
            "https://olx-ticketing-frontend.vercel.app",
            re.compile(r"https://.*\.vercel\.app")   # ✅ compiled regex for any Vercel URL
        ],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# ✅ SQLAlchemy config (after app is initialized)
from flask_sqlalchemy import SQLAlchemy
print("✅ DB URL loaded:", os.environ.get("SUPABASE_DB_URL"))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SUPABASE_DB_URL')  # Uses Neon
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ✅ Keep database connection alive (Neon fix)
with app.app_context():
    try:
        db.session.execute("SELECT 1")
        print("✅ Database connection verified")
    except Exception as e:
        print("⚠️ DB warm-up failed:", e)

# ✅ Ticket database model
class Ticket(db.Model):
    __tablename__ = 'tickets'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    email = db.Column(db.String)
    description = db.Column(db.Text)
    status = db.Column(db.String, default='Received')
    service_type = db.Column(db.String)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

from time import time

# Track last submission times by email
last_submission_times = {}

@app.route('/tickets', methods=['POST'])
def submit_ticket():
    data = request.get_json()
    print("🔁 Incoming data:", data)

    if not data:
        return jsonify({'error': 'Invalid JSON received'}), 400

    name = data.get('full_name')
    department = data.get('department')
    email = (data.get('email') or "").strip().lower()
    service_type = data.get('subject')
    description = data.get('message')

    if not all([name, email, service_type, description]):
        return jsonify({'error': 'Missing fields'}), 400

    allowed_domain = (os.getenv("ALLOWED_DOMAIN", "@olx.com.lb") or "").strip().lower()
    print(f"🔎 EMAIL={repr(email)}  ALLOWED_DOMAIN={repr(allowed_domain)}")

    if not re.search(re.escape(allowed_domain) + r'$', email):
        return jsonify({'status': 'forbidden', 'message': f'Only {allowed_domain} emails are allowed'}), 403

    # ✅ Cooldown check (10 seconds)
    now = time()
    if email in last_submission_times and now - last_submission_times[email] < 2:
        print("⚠️ Rapid submission detected.")
        return jsonify({
            'status': 'cooldown',
            'message': 'You recently submitted a ticket. Please wait a few seconds before trying again.'
        }), 200

    # ✅ Update last submission time
    last_submission_times[email] = now

    try:
        # ✅ Check for same ticket in last 10 minutes
        ten_minutes_ago = datetime.utcnow() - timedelta(minutes=10)
        existing_ticket = Ticket.query.filter_by(
            email=email,
            service_type=service_type,
            description=description,
            status="Received"
        ).filter(Ticket.created_at >= ten_minutes_ago).first()

        if existing_ticket:
            print("⚠️ Duplicate ticket detected.")
            return jsonify({
                'status': 'duplicate',
                'message': 'This ticket has already been submitted recently.',
                'ticket_id': existing_ticket.id
            }), 200

        # ✅ Create and store new ticket
        ticket = Ticket(
            name=name,
            email=email,
            service_type=service_type,
            description=description,
            status="Received"
        )

        db.session.add(ticket)
        db.session.commit()

        ticket_id = ticket.id
        subject_with_id = f"[Ticket #{ticket_id}] {service_type}"

        body = f"""\
🎫 Ticket #{ticket_id}

Service Type: {service_type}
Name: {name}
Department: {department}
Email: {email}

Message:
{description}
"""

        send_email(subject_with_id, body)
        print(f"✅ Ticket #{ticket_id} submitted and email sent.")

        return jsonify({'status': 'success', 'ticket_id': ticket_id}), 201

    except Exception as e:
        print("❌ Runtime Error:", e)
        return jsonify({'error': str(e)}), 500

# ✅ Email Function — uses Gmail App Password (secure)
def send_email(subject, body):
    sender = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")
    receiver = sender  # Can be changed if needed

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = receiver

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(sender, password)
        smtp.sendmail(sender, receiver, msg.as_string())

# ✅ Root Route for health check
@app.route('/', methods=['GET'])
def home():
    return "Internal Ticketing System is running ✅"

# ✅ Start Flask app with context
if __name__ == '__main__':
    with app.app_context():
        app.run(debug=True, port=5050)