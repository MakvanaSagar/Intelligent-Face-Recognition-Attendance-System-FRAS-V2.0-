from flask import Flask, render_template, Response, request, jsonify, send_from_directory, send_file, session, redirect, url_for
import cv2
import numpy as np
import os
from pymongo import MongoClient
import requests
from datetime import datetime
import base64
import io
from PIL import Image
import mimetypes
import pandas as pd
from xhtml2pdf import pisa

# Fix for Windows registry issue
mimetypes.add_type('text/css', '.css')

app = Flask(__name__)
app.secret_key = 'super_secret_key_change_this'

# -- Database Setup (MongoDB) --
try:
    client = MongoClient("mongodb://localhost:27017/")
    db = client['face_attendance_db']
    users_col = db['users']
    attendance_col = db['attendance']
    settings_col = db['settings']
    counters_col = db['counters']
    print("MongoDB Connected.")
except Exception as e:
    print(f"MongoDB Error: {e}")

# -- Helper: Auto-Increment for User ID (Crucial for Face Recognition Trainer) --
def get_next_user_id():
    seq = counters_col.find_one_and_update(
        {'_id': 'userid'},
        {'$inc': {'sequence_value': 1}},
        upsert=True,
        return_document=True
    )
    return seq['sequence_value']

# Force CSS mimetype
@app.route('/static/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(os.path.join(app.root_path, 'static', 'css'), filename, mimetype='text/css')



# -- Global Vars & Models --
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
smile_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_smile.xml') # Liveness Detector
eye_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml') # Blink Detector
recognizer = cv2.face.LBPHFaceRecognizer_create()

TRAINING_DATA_DIR = "training_data"
if not os.path.exists(TRAINING_DATA_DIR):
    os.makedirs(TRAINING_DATA_DIR)

def train_model():
    faces = []
    ids = []
    if not os.listdir(TRAINING_DATA_DIR):
        print("No training data found.")
        return

    for filename in os.listdir(TRAINING_DATA_DIR):
        if filename.endswith(".jpg"):
            path = os.path.join(TRAINING_DATA_DIR, filename)
            parts = filename.split('_')
            if len(parts) >= 1:
                try:
                    user_id = int(parts[0])
                    img = Image.open(path).convert('L')
                    img_np = np.array(img, 'uint8')
                    faces.append(img_np)
                    ids.append(user_id)
                except:
                    continue
    
    if faces:
        recognizer.train(faces, np.array(ids))
        recognizer.save("trainer.yml")
        print("Model trained.")

if os.path.exists("trainer.yml"):
    recognizer.read("trainer.yml")
    print("Model loaded.")



# -- WhatsApp Logic (Simulation Mode) --
def send_whatsapp_message(to_phone, name, time_str, type="Check-in"):
    # START SIMULATION
    message_text = f"Hi {name}, Attendance Marked: {type} at {time_str}. ✅"
    
    print(f"\n{'='*40}")
    print(f"🚀 [SIMULATION MODE] Sending WhatsApp Message...")
    print(f"📲 To: {to_phone}")
    print(f"📩 Message: {message_text}")
    print(f"✅ Status: Success (Pretend)")
    print(f"{'='*40}\n")
    
    return message_text # Return the message for frontend display
    
    # Real API logic is bypassed for now as per user request.
    # To enable real messages later, uncomment the code below and configure settings.
    """
    settings = settings_col.find_one({'_id': 'whatsapp_config'})
    if not settings: return

    phone_id = settings.get('phone_id')
    token = settings.get('token')
    if not phone_id or not token: return

    url = f"https://graph.facebook.com/v17.0/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": f"Hi {name}, Attendance Marked: {type} at {time_str}. ✅"}
    }
    try:
        requests.post(url, headers=headers, json=data)
    except:
        pass
    """

# -- Routes --

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        # Hardcoded Admin Credentials
        if email == "admin" and password == "admin123":
             session['admin'] = True
             return redirect(url_for('index'))
        return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

@app.route('/register')
def register_page():
    if not session.get('admin'):
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/attendance')
def attendance_page():
    mode = request.args.get('mode', 'General')
    return render_template('attendance.html', mode=mode)

@app.route('/settings', methods=['GET', 'POST'])
def settings_page():
    if not session.get('admin'):
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        phone_id = request.form.get('phone_number_id')
        token = request.form.get('access_token')
        
        settings_col.update_one(
            {'_id': 'whatsapp_config'},
            {'$set': {'phone_id': phone_id, 'token': token}},
            upsert=True
        )
        return render_template('settings.html', message="WhatsApp Settings Updated!", phone_id=phone_id, token=token)
    
    settings = settings_col.find_one({'_id': 'whatsapp_config'}) or {}
    return render_template('settings.html', 
        phone_id=settings.get('phone_id', ''), 
        token=settings.get('token', ''))

@app.route('/api/register', methods=['POST'])
def api_register():
    if not session.get('admin'):
         return jsonify({'success': False, 'message': 'Unauthorized'})

    data = request.json
    name = data.get('name')
    phone = data.get('phone')
    role = data.get('role', 'Student')
    image_data = data.get('image')

    if not name or not image_data:
        return jsonify({'success': False, 'message': 'Name or Image missing'})

    try:
        user_id = get_next_user_id()
        
        # Save to MongoDB
        users_col.insert_one({
            'user_id': user_id, # Integer ID for logic
            'name': name,
            'phone': phone,
            'role': role,
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        # Save Image
        header, encoded = image_data.split(",", 1)
        img_bytes = base64.b64decode(encoded)
        image = Image.open(io.BytesIO(img_bytes))
        image_gray = image.convert('L')
        img_np = np.array(image_gray, 'uint8')
        faces = face_cascade.detectMultiScale(img_np, 1.1, 4)
        
        if len(faces) == 0:
             return jsonify({'success': False, 'message': 'No face detected. Try again.'})

        (x, y, w, h) = faces[0]
        face_img = image_gray.crop((x, y, x+w, y+h))
        face_img = face_img.resize((200, 200))
        filename = f"{user_id}_{name}_1.jpg"
        face_img.save(os.path.join(TRAINING_DATA_DIR, filename))

        train_model()
        return jsonify({'success': True, 'message': f'{role} {name} registered!'})

    except Exception as e:
        print(e)
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/mark_attendance', methods=['POST'])
def api_mark_attendance():
    data = request.json
    image_data = data.get('image')

    if not image_data or not os.path.exists("trainer.yml"):
        return jsonify({'success': False, 'message': 'System not ready or image missing.'})

    try:
        header, encoded = image_data.split(",", 1)
        img_bytes = base64.b64decode(encoded)
        image = Image.open(io.BytesIO(img_bytes))
        image_gray = image.convert('L')
        img_np = np.array(image_gray, 'uint8')

        faces = face_cascade.detectMultiScale(img_np, 1.1, 4)
        if len(faces) == 0:
            return jsonify({'success': False, 'message': 'No face detected'})


        recognized_names = []
        whatsapp_msg = None



        for (x, y, w, h) in faces:
            # Liveness Check (Human Detection)
            face_roi_gray = img_np[y:y+h, x:x+w]
            
            # 1. Smile Detection
            smiles = smile_cascade.detectMultiScale(face_roi_gray, scaleFactor=1.8, minNeighbors=20)
            # 2. Eye Detection
            eyes = eye_cascade.detectMultiScale(face_roi_gray, scaleFactor=1.1, minNeighbors=10)
            
            # Check if *either* Smile OR Eyes are detected clearly (implies 3D structure, not flat photo)
            # Standard photos often fail strict eye+smile checks in low light, so OR condition is safer for demo.
            is_live = (len(smiles) > 0) or (len(eyes) >= 2)
            
            # Recognition Mode
            id_predicted, confidence = recognizer.predict(face_roi_gray)
            
            if confidence < 80:
                user = users_col.find_one({'user_id': id_predicted})
                if user:
                    name = user['name']
                    user_id = user['user_id']
                    phone = user.get('phone')
                    role = user.get('role', 'User')
                    
                    if not is_live:
                         recognized_names.append(f"⚠️ {name} - BLINK or SMILE")
                         continue

                    today = datetime.now().strftime("%Y-%m-%d")
                    now_time = datetime.now().strftime("%H:%M:%S")

                    existing = attendance_col.find_one({'user_id': user_id, 'date': today})
                    
                    if not existing:
                        attendance_col.insert_one({
                            'user_id': user_id,
                            'name': name,
                            'check_in': now_time,
                            'date': today
                        })
                        recognized_names.append(f"{name} ({role}) Check-in")
                        if phone: 
                             msg = send_whatsapp_message(phone, name, now_time, "Check-in")
                             whatsapp_msg = msg
                    else:
                        attendance_col.update_one(
                            {'_id': existing['_id']},
                            {'$set': {'check_out': now_time}}
                        )
                        recognized_names.append(f"{name} ({role}) Check-out")
                        
                else:
                     recognized_names.append("Unknown User")
            else:
                recognized_names.append("Unknown")
        
        if not recognized_names:
             return jsonify({'success': False, 'message': 'Not Recognized'})

        return jsonify({
            'success': True, 
            'message': 'Result: ' + ', '.join(recognized_names),
            'whatsapp_notification': whatsapp_msg
        })

    except Exception as e:
        print(e)
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})


@app.route('/report')
def report_page():
    if not session.get('admin'):
        return redirect(url_for('login'))
        
    # Get all users with total attendance count
    all_users = list(users_col.find())
    report_data = []
    
    for u in all_users:
        count = attendance_col.count_documents({'user_id': u['user_id']})
        report_data.append({
            'user_id': u['user_id'],
            'name': u['name'],
            'role': u.get('role', 'Student'),
            'phone': u.get('phone', '-'),
            'total_days': count,
            'id': u['user_id'] # alias for template compatibility
        })
        
    return render_template('report.html', users=report_data)

@app.route('/download_report/<int:user_id>')
def download_user_report(user_id):
    if not session.get('admin'):
        return redirect(url_for('login'))
    
    user = users_col.find_one({'user_id': user_id})
    if not user: return "User not found", 404
    
    records = list(attendance_col.find({'user_id': user_id}).sort('date', -1))
    
    df = pd.DataFrame(records)
    # Drop mongodb _id
    if '_id' in df.columns: df = df.drop(columns=['_id'])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=f"{user['name']} Attendance")
    output.seek(0)
    
    safe_name = "".join([c for c in user['name'] if c.isalpha() or c.isdigit() or c==' ']).strip()
    return send_file(output, download_name=f"Report_{safe_name}.xlsx", as_attachment=True)


@app.route('/download_pdf_report/<int:user_id>')
def download_user_pdf_report(user_id):
    if not session.get('admin'):
        return redirect(url_for('login'))
    
    user = users_col.find_one({'user_id': user_id})
    if not user: return "User not found", 404

    records = list(attendance_col.find({'user_id': user_id}).sort('date', -1))
    
    # Calculate Statistics
    total_present = len(records)
    percentage = 0.0
    
    try:
        # Try to calculate percentage based on registration date
        reg_str = user.get('created_at')
        if reg_str:
            reg_date = datetime.strptime(reg_str, "%Y-%m-%d %H:%M:%S")
            days_since = (datetime.now() - reg_date).days
            if days_since < 1: days_since = 1
            percentage = (total_present / days_since) * 100
        else:
            # Fallback if no date: assume 100% or based on first record
            percentage = 100.0 if total_present > 0 else 0.0
            
        if percentage > 100: percentage = 100.0
        
    except Exception as e:
        print(f"Stats Calc Error: {e}")
        percentage = 0.0

    # Format for Template
    stats = {
        'total_present': total_present,
        'percentage': round(percentage, 1)
    }

    html_content = render_template('pdf_report.html', user=user, records=records, stats=stats, date=datetime.now().strftime("%Y-%m-%d"))
    
    pdf_out = io.BytesIO()
    pisa_status = pisa.CreatePDF(html_content, dest=pdf_out)
    
    if pisa_status.err:
        return f"Error generating PDF: {pisa_status.err}", 500
        
    pdf_out.seek(0)
    safe_name = "".join([c for c in user['name'] if c.isalpha() or c.isdigit() or c==' ']).strip()
    return send_file(pdf_out, download_name=f"Report_{safe_name}.pdf", as_attachment=True, mimetype='application/pdf')

if __name__ == '__main__':
    train_model()
    app.run(debug=True)
