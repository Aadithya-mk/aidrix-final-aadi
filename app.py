import os
import datetime
import json
import io
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, render_template, jsonify, request, send_file
from dotenv import load_dotenv
from google import genai 

# --- PDF LIBRARY CHECK ---
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    PDF_LIBRARY_AVAILABLE = True
except ImportError:
    PDF_LIBRARY_AVAILABLE = False
    print("⚠️ WARNING: 'reportlab' not found. PDF features will be disabled.")

# 1. SETUP & CONFIGURATION
load_dotenv()

# --- GEMINI AI SETUP ---
GENAI_API_KEY = os.getenv("GENAI_API_KEY")
client = genai.Client(api_key=GENAI_API_KEY)
model_id = "gemini-2.5-flash-lite" 

# Initialize Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate("service-account.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()
app = Flask(__name__)

# --- ROUTE HANDLERS ---
@app.route('/')
def home(): return render_template('index.html')

@app.route('/dashboard/user')
def user_dashboard(): return render_template('dashboard_user.html')

@app.route('/dashboard/worker')
def worker_dashboard(): return render_template('dashboard_worker.html')

@app.route('/dashboard/admin')
def admin_dashboard(): return render_template('dashboard_admin.html')

# --- 1. INTELLIGENT CHATBOT ---
@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    user_msg = data.get('message', '')
    if not user_msg: return jsonify({"reply": "How can I help you?"})

    try:
        system_instruction = """
        You are Aidrix, the AI assistant for the Aidrix Civic Platform.
        
        Your Knowledge Base:
        1. **Reporting**: Users upload photos/locations to report issues (potholes, garbage).
        2. **Gamification**: Users earn badges (Scout=1 report, Guardian=5, Legend=10).
        3. **Process**: Reports go to Admin -> Assigned to Worker -> Resolved.
        4. **Notifications**: Users get alerted when work is done.
        
        Keep answers short, helpful, and encouraging.
        """
        
        response = client.models.generate_content(
            model=model_id,
            contents=f"{system_instruction}\nUser: {user_msg}"
        )
        return jsonify({"reply": response.text})
    except Exception as e:
        print(f"AI Error: {e}")
        return jsonify({"reply": "I am currently offline. Please try again later."})

# --- 2. ACHIEVEMENT SYSTEM ---
@app.route('/api/user/achievements', methods=['GET'])
def get_achievements():
    email = request.args.get('email')
    try:
        docs = db.collection('reports').where('user_email', '==', email).stream()
        count = sum(1 for _ in docs)
        
        badges = [
            {"name": "Citizen Scout", "desc": "Reported your 1st issue", "icon": "bi-binoculars", "unlocked": count >= 1},
            {"name": "City Guardian", "desc": "Submitted 5+ reports", "icon": "bi-shield-check", "unlocked": count >= 5},
            {"name": "Aidrix Legend", "desc": "Top contributor (10+ reports)", "icon": "bi-trophy-fill", "unlocked": count >= 10}
        ]
        
        return jsonify({"report_count": count, "badges": badges})
    except: return jsonify({"report_count": 0, "badges": []})

# --- 3. PDF REPORT GENERATOR ---
@app.route('/api/admin/generate_pdf', methods=['GET'])
def generate_pdf():
    if not PDF_LIBRARY_AVAILABLE:
        return jsonify({"error": "Install reportlab library"}), 500
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        elements.append(Paragraph("<b>Aidrix - Civic Issue Report</b>", styles['Title']))
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
        elements.append(Spacer(1, 20))

        data = [['Status', 'Description', 'Reported By', 'Date']]
        
        docs = db.collection('reports').order_by('timestamp', direction=firestore.Query.DESCENDING).stream()
        for d in docs:
            rep = d.to_dict()
            desc = (rep.get('description')[:40] + '..') if len(rep.get('description')) > 40 else rep.get('description')
            raw_date = rep.get('timestamp', '')
            date_str = str(raw_date)[:10]
            
            data.append([
                rep.get('status', 'N/A'),
                desc,
                rep.get('user_email', 'Anon'),
                date_str
            ])

        t = Table(data, colWidths=[80, 250, 120, 80])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        
        elements.append(t)
        doc.build(elements)
        buffer.seek(0)
        
        return send_file(buffer, as_attachment=True, download_name='Aidrix_Report.pdf', mimetype='application/pdf')
    except Exception as e: return jsonify({"error": str(e)}), 500

# --- 4. CORE REPORT APIs ---

@app.route('/api/reports', methods=['POST'])
def submit_report():
    try:
        data = request.json
        db.collection('reports').add({
            'description': data.get('description'),
            'lat': data.get('lat'), 'lng': data.get('lng'),
            'status': 'Pending',
            'timestamp': str(datetime.datetime.now()), 
            'user_email': data.get('email'),
            'likes': 0, 'liked_by': [], 'comments': [],
            'has_image': data.get('has_image', False),
            'image': data.get('image', None)
        })
        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/reports/feed', methods=['GET'])
def get_feed():
    try:
        docs = db.collection('reports').stream()
        feed = []
        for doc in docs:
            r = doc.to_dict(); r['id'] = doc.id
            feed.append(r)
        feed.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return jsonify(feed)
    except: return jsonify([])

@app.route('/api/reports/update', methods=['POST'])
def update_report():
    try:
        data = request.json
        rid = data.get('id')
        status = data.get('status')
        worker = data.get('worker_email', 'Worker')
        
        report_ref = db.collection('reports').document(rid)
        report_data = report_ref.get().to_dict()
        user_email = report_data.get('user_email')
        desc = report_data.get('description')

        report_ref.update({'status': status})
        
        ts = str(datetime.datetime.now())

        if status == 'Resolved':
            # Notify Admin
            db.collection('notifications').add({
                'target_email': 'admin@aidrix.com', 
                'message': f"Issue Resolved by {worker}: {desc}", 
                'timestamp': ts
            })
            # Notify User
            if user_email:
                db.collection('notifications').add({
                    'target_email': user_email,
                    'message': f"✅ Good News! Your report '{desc}' has been fixed.",
                    'timestamp': ts
                })

        return jsonify({"status": "success"})
    except Exception as e: return jsonify({"error": str(e)}), 500

# --- UPDATED: Assign Report (Gets Description) ---
@app.route('/api/reports/assign', methods=['POST'])
def assign_report():
    try:
        data = request.json
        rid = data.get('report_id')
        worker_email = data.get('worker_email')
        
        # 1. Fetch Report Description
        report_ref = db.collection('reports').document(rid)
        report_doc = report_ref.get()
        
        description = "Maintenance Task"
        if report_doc.exists:
            description = report_doc.to_dict().get('description', 'Maintenance Task')
            if len(description) > 30: description = description[:30] + "..."

        # 2. Update Status
        report_ref.update({
            'assigned_to': worker_email,
            'status': 'In Progress'
        })
        
        # 3. Notify with Description
        db.collection('notifications').add({
            'target_email': worker_email,
            'message': f"New Assignment: {description}", 
            'timestamp': str(datetime.datetime.now())
        })
        return jsonify({"status": "success"})
    except Exception as e: 
        print(e)
        return jsonify({"error": "Failed"}), 500

@app.route('/api/reports/delete', methods=['POST'])
def delete_report():
    db.collection('reports').document(request.json['id']).delete()
    return jsonify({"status": "success"})

# --- 5. WORKER/USER/AI HELPERS ---

@app.route('/api/ai/analyze', methods=['GET'])
def ai_analyze_reports():
    try:
        docs = db.collection('reports') \
            .order_by('timestamp', direction=firestore.Query.DESCENDING) \
            .limit(30).stream()

        reports = []
        for doc in docs:
            d = doc.to_dict()
            reports.append({
                "id": doc.id,
                "desc": d.get('description'),
                "lat": d.get('lat'),
                "lng": d.get('lng'),
                "user_email": d.get('user_email')  # ✅ ADDED (name fix)
            })

        if not reports:
            return jsonify({"duplicates": [], "priorities": {}})

        prompt = f"""
Analyze these civic reports and detect duplicates.

STRICT RULES:
- Use ONLY the provided IDs
- NEVER invent IDs
- Every duplicate MUST contain a valid "id" from input
- Return ONLY JSON (no text, no markdown)

FORMAT:
{{
  "duplicates": [
    {{
      "id": "existing_report_id",
      "reason": "duplicate reason"
    }}
  ],
  "priorities": {{
    "existing_report_id": {{
      "score": 90,
      "reason": "Hazard"
    }}
  }}
}}

Reports:
{json.dumps(reports)}
"""

        response = client.models.generate_content(
            model=model_id,
            contents=prompt
        )

        text = response.text.strip().replace("```json", "").replace("```", "").strip()
        return jsonify(json.loads(text))

    except Exception as e:
        print("AI ANALYZE ERROR:", e)
        return jsonify({"duplicates": [], "priorities": {}})

@app.route('/api/workers/pending', methods=['GET'])
def get_pending_workers():
    docs = db.collection('users').where('role', '==', 'worker').where('isVerified', '==', False).stream()
    return jsonify([{'uid': d.id, **d.to_dict()} for d in docs])

@app.route('/api/workers/verified', methods=['GET'])
def get_verified_workers():
    docs = db.collection('users').where('role', '==', 'worker').where('isVerified', '==', True).stream()
    return jsonify([{'uid': d.id, **d.to_dict()} for d in docs])

@app.route('/api/workers/approve', methods=['POST'])
def approve_worker():
    db.collection('users').document(request.json['uid']).update({'isVerified': True})
    return jsonify({"status": "success"})

@app.route('/api/workers/delete', methods=['POST'])
def delete_worker():
    db.collection('users').document(request.json['uid']).delete()
    return jsonify({"status": "success"})

@app.route('/api/user/profile', methods=['GET', 'POST'])
def user_profile():
    if request.method == 'POST':
        data = request.json
        db.collection('users').document(data['uid']).set(data, merge=True)
        return jsonify({"status": "success"})
    doc = db.collection('users').document(request.args.get('uid')).get()
    return jsonify(doc.to_dict() if doc.exists else {})

# --- UPDATED: Notifications (Sends ID) ---
@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    email = request.args.get('email')
    try:
        docs = db.collection('notifications').where('target_email', '==', email).stream()
        notifs = []
        for doc in docs:
            notifs.append({'id': doc.id, **doc.to_dict()})
            
        notifs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return jsonify(notifs[:10]) 
    except: return jsonify([])

# --- NEW: Delete Notification ---
@app.route('/api/notifications/delete', methods=['POST'])
def delete_notification():
    try:
        notif_id = request.json.get('id')
        db.collection('notifications').document(notif_id).delete()
        return jsonify({"status": "success"})
    except: return jsonify({"error": "Failed"}), 500

@app.route('/api/reports/history', methods=['GET'])
def get_history():
    email = request.args.get('email')
    try:
        docs = db.collection('reports').where('user_email', '==', email).stream()
        history = []
        for doc in docs:
            r = doc.to_dict(); r['id'] = doc.id
            history.append(r)
        history.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return jsonify(history)
    except: return jsonify([])

@app.route('/api/reports/like', methods=['POST'])
def like_report():
    data = request.json
    ref = db.collection('reports').document(data['id'])
    doc = ref.get().to_dict()
    if data['user_email'] in doc.get('liked_by', []):
        ref.update({'likes': firestore.Increment(-1), 'liked_by': firestore.ArrayRemove([data['user_email']])})
    else:
        ref.update({'likes': firestore.Increment(1), 'liked_by': firestore.ArrayUnion([data['user_email']])})
    return jsonify({"status": "success"})

@app.route('/api/reports/comment', methods=['POST'])
def add_comment():
    data = request.json
    db.collection('reports').document(data['id']).update({
        'comments': firestore.ArrayUnion([{
            'text': data.get('text'), 'user': data.get('user_email'), 'time': str(datetime.datetime.now())
        }])
    })
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True)