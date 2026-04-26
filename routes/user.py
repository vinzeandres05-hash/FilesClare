from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, send_from_directory
from db import execute_query 
from functools import wraps
import random
import time
import os
import requests
import base64

# Create Blueprint for User Routes
user_bp = Blueprint('user', __name__, url_prefix='/')

# =========================================================
# USER HELPER FUNCTIONS 
# =========================================================

# ---------------------------------------------------------
# NEW: BREVO EMAIL FUNCTION (REPLACED FLASK-MAIL)
# ---------------------------------------------------------
def send_otp_email(recipient_email, otp_code):
    """Sends OTP via Brevo API instead of SMTP to avoid Render timeouts."""
    url = "https://api.brevo.com/v3/smtp/email"
    
    # Kinukuha ang config mula sa iyong config.py
    api_key = current_app.config.get('BREVO_API_KEY')
    sender_email = current_app.config.get('BREVO_SENDER_EMAIL')
    sender_name = current_app.config.get('BREVO_SENDER_NAME')

    if not api_key:
        print("ERROR: BREVO_API_KEY is not set or loaded properly.")
        return False
    if not sender_email:
        print("ERROR: BREVO_SENDER_EMAIL is not configured.")
        return False

    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json"
    }

    # Pinanatili ko ang maganda mong HTML design
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            .email-container {{ font-family: sans-serif; background-color: #f4f4f4; padding: 20px; }}
            .card {{ max-width: 500px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }}
            .header {{ background-color: #0f111a; padding: 30px; text-align: center; }}
            .header h2 {{ color: #2cc5ad; margin: 0; letter-spacing: 1px; }}
            .content {{ padding: 40px 30px; text-align: center; color: #333333; }}
            .otp-box {{ background-color: #f0fdfa; border: 2px dashed #2cc5ad; padding: 20px; margin: 25px 0; border-radius: 8px; }}
            .otp-code {{ font-size: 32px; font-weight: bold; color: #0f111a; letter-spacing: 5px; }}
            .footer {{ background-color: #fafafa; padding: 20px; text-align: center; font-size: 12px; color: #888888; }}
        </style>
    </head>
    <body>
        <div class="email-container">
            <div class="card">
                <div class="header"><h2>CLAREFILES SYSTEM</h2></div>
                <div class="content">
                    <p>Hello,</p>
                    <p>Your One-Time Passcode (OTP) for the Document Request System is:</p>
                    <div class="otp-box"><div class="otp-code">{otp_code}</div></div>
                    <p style="color: #ff4d4d;">This code will expire in <b>5 minutes</b>.</p>
                </div>
                <div class="footer">&copy; 2026 Document Request System</div>
            </div>
        </div>
    </body>
    </html>
    """

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": recipient_email}],
        "subject": "Document Request Verification Code",
        "htmlContent": html_body
    }

    try:
        print(f"DEBUG: Sending Brevo email to {recipient_email}, api_key set? {bool(api_key)}")
        # print(f"DEBUG: API key starts with: {api_key[:20] if api_key else 'None'}...")
        print(f"DEBUG: Sender email: {sender_email}")
        # print("ACTUAL BREVO KEY BEING USED:", repr(current_app.config.get('BREVO_API_KEY')))
        response = requests.post(url, json=payload, headers=headers)
        print("DEBUG: Brevo response", response.status_code, response.text)
        if response.status_code in [200, 201, 202]:
            return True
        else:
            print(f"BREVO ERROR: {response.text}")
            return False
    except Exception as e:
        print(f"CONNECTION ERROR: {e}")
        return False
# ---------------------------------------------------------
# END: EMAIL FUNCTION 
# ---------------------------------------------------------

def get_student_info(email):
    """Retrieving complete student profile data."""
    query = "SELECT * FROM student_info WHERE requester_email = %s"
    return execute_query(query, (email,), fetch_one=True)

def get_document_types():
    """Retrieving the list of available documents and fees."""
    query = "SELECT * FROM document_types ORDER BY doc_name"
    return execute_query(query, fetch_all=True)

# =========================================================
# USER ROUTES
# =========================================================

@user_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        print("DEBUG: /login POST reached", request.form)
        email = request.form.get('email')

        # Start user auth flow with a clean admin session scope.
        session.pop('admin_id', None)
        session.pop('admin_email', None)
        session.pop('admin_role', None)
        session.pop('admin_fullname', None)
        session.pop('admin_authenticated', None)
        
        # 1. I-check muna kung existing ang user at kung ano ang status niya
        user_data = execute_query("SELECT email, status FROM users WHERE email = %s", (email,), fetch_one=True)
        
        if user_data:
            # DITO NATIN SIYA HAHARANGIN
            if user_data['status'] == 'Blocked':
                flash("Your account has been blocked by the administrator. Please contact support.", "danger")
                return render_template('login.html')

        # 2. Generate and Store the OTP session (Tuloy ang proseso kung Active o New User)
        otp_code = str(random.randint(100000, 999999)) 
        session['temp_email'] = email
        session['otp_code'] = otp_code
        session['otp_expiry'] = int(time.time()) + 300 # 5 minutes expiry
        session['otp_requested_at'] = int(time.time())

        # 3. send the OTP 
        if send_otp_email(email, otp_code):
            print(f"DEBUG: OTP {otp_code} sent successfully to {email}.")
            return redirect(url_for('user.verify_otp'))
        else:
            flash("Failed to send verification email. Please try again.", "danger")
            return render_template('login.html')
    
    if 'user_email' in session:
        return redirect(url_for('user.dashboard'))
    return render_template('login.html')

@user_bp.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if 'temp_email' not in session:
        return redirect(url_for('user.login'))
    email_to_verify = session['temp_email']

    if request.method == 'POST':
        user_input_code = request.form.get('otp_input')
        current_time = int(time.time())

        if user_input_code == session.get('otp_code') and current_time < session.get('otp_expiry', 0):
            
            # 1. Check if user exists (for first-time login/registration)
            user = execute_query("SELECT email FROM users WHERE email = %s", (email_to_verify,), fetch_one=True)
            is_new_user = not user
            
            if is_new_user:
                # Insert user and create empty student_info profile (Auto-Registration)
                execute_query("INSERT INTO users (email, status, role) VALUES (%s, %s, %s)", (email_to_verify, 'Active', 'student'))
                execute_query("INSERT INTO student_info (requester_email) VALUES (%s)", (email_to_verify,))
            
            # 2. Log In the user
            session.pop('admin_id', None)
            session.pop('admin_email', None)
            session.pop('admin_role', None)
            session.pop('admin_fullname', None)
            session.pop('admin_authenticated', None)
            session['user_email'] = email_to_verify 
            session.pop('otp_code', None)
            session.pop('otp_expiry', None)
            session.pop('temp_email', None)
            
            if is_new_user:
                flash("Welcome! Please complete your profile to continue.", "info")
                return redirect(url_for('user.student_info'))
            
            flash("Login successful! Welcome.", "success")
            return redirect(url_for('user.dashboard')) 
        
        else:
            flash("Invalid or expired code. Please try again.", "danger")
            return render_template('verify_otp.html', email=email_to_verify)

    return render_template('verify_otp.html', email=email_to_verify)

# --- BAGONG ROUTE PARA SA RESEND CODE ---
@user_bp.route('/resend-otp')
def resend_otp():
    """Route to resend OTP code."""
    email = session.get('temp_email')
    
    if not email:
        flash("Session expired. Please log in again.", "danger")
        return redirect(url_for('user.login'))

    now = int(time.time())
    last_sent = session.get('otp_requested_at', 0)
    if now - last_sent < 30:
        flash("Please wait a few seconds before requesting a new code.", "warning")
        return redirect(url_for('user.verify_otp'))

    # Mag-generate ng bagong code
    otp_code = str(random.randint(100000, 999999))
    session['otp_code'] = otp_code
    session['otp_expiry'] = now + 300
    session['otp_requested_at'] = now

    print(f"DEBUG: /resend-otp called for {email}, new OTP {otp_code} generated.")
    if send_otp_email(email, otp_code):
        flash("A new verification code has been sent to your email.", "success")
    else:
        flash("Failed to resend code. Please try again later.", "danger")
    
    return redirect(url_for('user.verify_otp'))

@user_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('user_email', None)
    session.pop('temp_email', None)
    session.pop('otp_code', None)
    session.pop('otp_expiry', None)
    session.pop('otp_requested_at', None)
    session.pop('admin_id', None)
    session.pop('admin_email', None)
    session.pop('admin_role', None)
    session.pop('admin_fullname', None)
    session.pop('admin_authenticated', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('user.login'))

@user_bp.route('/', endpoint='dashboard')
def dashboard():
    if 'user_email' not in session: return redirect(url_for('user.login'))
    
    user_email = session['user_email']

    student_data = get_student_info(user_email)
    
    total_requests_result = execute_query(
        "SELECT COUNT(*) AS total_requests FROM requests WHERE requester_email = %s", 
        (user_email,), fetch_one=True
    )
    pending_count_result = execute_query(
        "SELECT COUNT(*) AS pending_count FROM requests WHERE requester_email = %s AND status='Pending'", 
        (user_email,), fetch_one=True
    )
    unpaid_bill_result = execute_query(
        "SELECT SUM(final_price) AS unpaid_bill FROM requests WHERE requester_email = %s AND status='Accepted'", 
        (user_email,), fetch_one=True
    )

    total_requests = total_requests_result.get('total_requests', 0) if isinstance(total_requests_result, dict) else 0
    pending_count = pending_count_result.get('pending_count', 0) if isinstance(pending_count_result, dict) else 0
    unpaid_bill = unpaid_bill_result.get('unpaid_bill', 0.0) if isinstance(unpaid_bill_result, dict) else 0.0
    unpaid_bill = unpaid_bill if unpaid_bill is not None else 0.0
    current_user = student_data.get('firstname') if student_data and student_data.get('firstname') else user_email
   
    return render_template('user_dashboard.html', 
                           current_user=current_user,
                           student=student_data,
                           total_requests=total_requests,
                           pending_count=pending_count,
                           unpaid_bill=unpaid_bill,
                           active_page='user_dashboard')

@user_bp.route('/profile', methods=['GET', 'POST'], endpoint='student_info')
def student_info():
    if 'user_email' not in session: return redirect(url_for('user.login'))
        
    user_email = session['user_email']
    if request.method == 'POST':
        lastname = request.form.get('lastname') or None
        firstname = request.form.get('firstname') or None
        middlename = request.form.get('middlename') or None
        suffix = request.form.get('suffix') or None
        gender = request.form.get('gender') or None
        age = request.form.get('age')
        contact = request.form.get('contact')
        birthdate = request.form.get('birthdate') or None
        enrollment_status = request.form.get('enrollment_status') or None
        education_level = request.form.get('education_level') or None
        track = request.form.get('track') or None
        course_grade = request.form.get('course_grade') or None
        student_id = request.form.get('student_id') or None
        address = request.form.get('address') or None

        if age is not None and age.strip() == '':
            age = None
        elif age is not None:
            try:
                age = int(age)
            except ValueError:
                age = None

        # MySQL UPSERT logic (INSERT ... ON DUPLICATE KEY UPDATE)
        query = '''
            INSERT INTO student_info (requester_email, lastname, firstname, middlename, gender, age, contact, birthdate, 
                                      suffix, enrollment_status, education_level, track, course_grade, student_id, address) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                lastname=VALUES(lastname), firstname=VALUES(firstname), middlename=VALUES(middlename), 
                suffix=VALUES(suffix), gender=VALUES(gender), age=VALUES(age), contact=VALUES(contact), birthdate=VALUES(birthdate), 
                enrollment_status=VALUES(enrollment_status), education_level=VALUES(education_level),
                track=VALUES(track), course_grade=VALUES(course_grade), student_id=VALUES(student_id), address=VALUES(address)
            '''
        params = (user_email, lastname, firstname, middlename, gender, age, contact, birthdate, 
                  suffix, enrollment_status, education_level, track, course_grade, student_id, address)

        print("DEBUG: Saving student profile for", user_email)
        print("DEBUG: student_info params", params)
        saved = execute_query(query, params)
        if saved:
            flash("Profile successfully updated!", "success")
        else:
            print("DEBUG: Profile save failed for", user_email)
            flash("Unable to save profile. Please check your entries and try again.", "danger")
        return redirect(url_for('user.student_info'))
    
    student_data = get_student_info(user_email)
    
    return render_template('student_info.html',student=student_data, active_page='student_info')


@user_bp.route('/new-request', methods=['GET', 'POST'])
def new_request():
    if 'user_email' not in session: return redirect(url_for('user.login'))
        
    user_email = session['user_email']
    student_data = get_student_info(user_email)
    document_types = get_document_types()

    # Filter documents based on student's education level
    student_level = student_data.get('education_level') if student_data else None
    if student_level:
        document_types = [d for d in document_types if d['education_level'] in ('All', student_level)]

    if request.method == 'POST':
        if not student_data or not student_data.get('lastname') or not student_data.get('address'):
            flash("Please fill out your Profile (including address) before submitting!", "danger")
            return redirect(url_for('user.student_info'))

        document_type = request.form['document_type']
        purpose = request.form['purpose']
        year_entry = request.form['year_entry']
        last_school = request.form['last_school']
        delivery_method = request.form.get('delivery_method', 'Pick-up')
        delivery_address = request.form.get('delivery_address')
        # admin_ = request.form.get('admin_id')

        query = '''
            INSERT INTO requests (requester_email, lastname, firstname, email, purpose, document, year_entry, last_school, course_grade, address, delivery_method, delivery_address, student_id) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'''
        params = (user_email, student_data['lastname'], student_data['firstname'], user_email, purpose, document_type, year_entry, last_school, student_data['course_grade'], student_data['address'], delivery_method, delivery_address, student_data['student_id'])
        
        execute_query(query, params)
        notif_msg = f"New request submitted by {student_data['firstname']} {student_data['lastname']}"
        execute_query("INSERT INTO notifications (message, category) VALUES (%s, 'request')", (notif_msg,))
        flash("Document Request successfully submitted!", "success")
        return redirect(url_for('user.history')) 

    delivery_options = ['Pick-up', 'Door-to-Door Delivery / Add Another Fee'] 

    return render_template('new_request.html',student=student_data, document_types=document_types, delivery_options=delivery_options, active_page='new_request')

@user_bp.route('/my-requests', endpoint='history')
def history():
    if 'user_email' not in session: return redirect(url_for('user.login'))
        
    user_email = session['user_email']
    query = 'SELECT * FROM requests WHERE requester_email = %s ORDER BY id DESC'
    history_data = execute_query(query, (user_email,), fetch_all=True)
        
    return render_template('history.html', request_history=history_data, active_page='history')

@user_bp.route('/download-document/<int:req_id>')
def download_document(req_id):
    if 'user_email' not in session:
        return redirect(url_for('user.login'))
    user_email = session['user_email']
    row = execute_query(
        'SELECT document_file_path, document FROM requests WHERE id = %s AND requester_email = %s',
        (req_id, user_email), fetch_one=True
    )
    if not row or not row.get('document_file_path'):
        flash("Digital copy is not available for this request.", "warning")
        return redirect(url_for('user.history'))
    upload_folder = os.path.join(current_app.static_folder, 'uploads', 'completed_docs')
    filename = os.path.basename(row['document_file_path'])
    download_name = f"Digital_Copy_{row['document']}_{req_id}.pdf"
    return send_from_directory(upload_folder, filename, as_attachment=True, download_name=download_name)

@user_bp.route('/verify/<string:token>')
def verify_document(token):
    doc = execute_query(
        '''SELECT r.id, r.document, r.status, r.updated_at, r.verification_token,
                  r.delivery_method, s.firstname, s.lastname
           FROM requests r
           LEFT JOIN student_info s ON r.requester_email = s.requester_email
           WHERE r.verification_token = %s AND r.status = 'Completed' ''',
        (token,), fetch_one=True
    )
    return render_template('verify_document.html', doc=doc, token=token)

@user_bp.route('/available-documents')
def available_documents():
    if 'user_email' not in session: return redirect(url_for('user.login'))
    user_email = session['user_email']
    student_data = get_student_info(user_email)
    document_types = get_document_types()
    # Filter documents based on student's education level
    student_level = student_data.get('education_level') if student_data else None
    if student_level:
        document_types = [d for d in document_types if d['education_level'] in ('All', student_level)]
    return render_template('available_documents.html', documents=document_types, active_page='available_documents')

@user_bp.route('/payments')
def payment():
    if 'user_email' not in session: 
        return redirect(url_for('user.login'))
        
    user_email = session['user_email']
    student_data = get_student_info(user_email)
    current_user = student_data.get('firstname') if student_data and student_data.get('firstname') else user_email
    
    query = """
    SELECT 
        r.id, r.document, r.final_price, r.status,
        CASE 
            -- 1. Kung may record sa payments table, gamitin ang status doon
            WHEN p.payment_status IS NOT NULL THEN p.payment_status
            
            -- 2. Kung burado na sa payments table pero 'Processing' o pataas ang request, ituring na PAID
            WHEN r.status IN ('Processing', 'Ready for pickup', 'Ready for delivery', 'Completed') THEN 'PAID'
            
            -- 3. Sa lahat ng ibang kaso (kasama ang deleted na rejected payment), ituring na UNPAID
            ELSE 'UNPAID'
        END as payment_status
    FROM requests r
    LEFT JOIN payments p ON r.id = p.request_id
    WHERE r.requester_email = %s 
    AND r.status IN ('Accepted', 'Ready for pickup', 'Ready for delivery', 'Processing', 'Completed', 'PAID') 
    AND r.final_price > 0.0 
    ORDER BY r.id DESC
    """
    
    billable_requests = execute_query(query, (user_email,), fetch_all=True)
    total_bill = sum(float(req['final_price']) for req in billable_requests if req['final_price'] is not None) if billable_requests else 0.0
    
    return render_template('payment.html',  
                           bills=billable_requests, 
                           total=total_bill, 
                           active_page='payment')

#API Key for PayMongo 
PAYMONGO_SECRET_KEY = os.getenv("PAYMONGO_SECRET_KEY") 

@user_bp.route('/get-payment-link/<int:req_id>')
def get_payment_link(req_id):
    # 1. Kunin ang amount at document name sa DB
    query = "SELECT document, final_price FROM requests WHERE id = %s"
    row = execute_query(query, (req_id,), fetch_one=True)
    
    if not row:
        return {"error": "Request not found"}, 404

    # 2. PayMongo API Setup
    url = "https://api.paymongo.com/v1/links"
    
    # Ang amount ay dapat centavos (PHP 100.00 = 10000)
    amount_in_centavos = int(float(row['final_price']) * 100)
    
    payload = {
        "data": {
            "attributes": {
                "amount": amount_in_centavos,
                "description": f"Payment for {row['document']} (ID: {req_id})",
                "remarks": str(req_id),
                # ETO YUNG IDUDUGTONG MO:
                "redirect": {
                    "success": url_for('user.payment_success', _external=True),
                    "failed": url_for('user.payment', _external=True)
                }
            }
        }
    }

    # Auth Header (Secret Key)
    auth_str = f"{PAYMONGO_SECRET_KEY}:"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Basic {encoded_auth}"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()
        # I-return ang checkout URL sa frontend
        return {"checkout_url": data['data']['attributes']['checkout_url']}
    except Exception as e:
        return {"error": str(e)}, 500

@user_bp.route('/payment-success')
def payment_success():
    if 'user_email' not in session: 
        return redirect(url_for('user.login'))
    
    flash("Payment successful! Your transaction has been processed.", "success")
    return redirect(url_for('user.payment'))

@user_bp.route('/help-support', endpoint='help_support')
def help_support():
    if 'user_email' not in session: return redirect(url_for('user.login'))
    return render_template('help_support.html', 
                            
                           active_page='help_support')

@user_bp.route('/submit-message', methods=['POST'])
def submit_message():
    if 'user_email' not in session:
        return redirect(url_for('user.login'))

    user_email = session['user_email'] # Dahil ito ang sine-set mo sa verify_otp
    msg = request.form.get('message_content')

    if user_email and msg:
        # Kunin ang ID ng user gamit ang email sa session
        user = execute_query("SELECT id FROM users WHERE email = %s", (user_email,), fetch_one=True)
        if user:
            execute_query(
                "INSERT INTO student_messages (user_id, message_text) VALUES (%s, %s)",
                (user['id'], msg)
            )
            return redirect(url_for('user.help_support'))
            
    return "Error: User not found or message empty", 400