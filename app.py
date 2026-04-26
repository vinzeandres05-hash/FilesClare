from dotenv import load_dotenv
load_dotenv(override=True)
from flask import Flask, request, jsonify
import requests
import os 
from db import create_tables, execute_query
from config import Config #
from routes.user import user_bp 
from routes.admin import admin_bp
from routes.user_uploadproof import upload_bp
from routes.admin_payments import admin_pay_bp


# =========================================================
# FLASK APP SETUP & CONFIGURATION
# =========================================================
app = Flask(__name__)
# NEW: Load configuration from Config class
app.config.from_object(Config) 

print("DEBUG: BREVO_API_KEY loaded?", bool(app.config.get('BREVO_API_KEY')))
print("DEBUG: BREVO_SENDER_EMAIL:", app.config.get('BREVO_SENDER_EMAIL'))

if app.config.get('BREVO_API_KEY'):
    key = app.config.get('BREVO_API_KEY')
    print(f"DEBUG: API Key preview: {key[:30]}...")
else:
    print("DEBUG: WARNING - BREVO_API_KEY is NOT loaded!")

app.secret_key = app.config.get('SECRET_KEY', 'YOUR_SUPER_SECURE_SECRET_KEY_HERE_2025')

print(f"DEBUG: Secret Key is {app.config.get('SECRET_KEY')}")

# mail = Mail(app) # Initialize mail object on the app

# =========================================================
# GLOBAL CONTEXT PROCESSOR (Para sa Sidebar Badges)
# =========================================================

# =========================================================
# webhook para sa PayMongo payment verification
# =========================================================

import re  # Siguraduhin na nasa taas ito para sa Regex

def send_payment_verified_email(student_email, student_name, request_id, document_name):
    """
    Dedicated function to send the 'Processing' email after PayMongo payment.
    """
    import requests as py_requests
    from flask import current_app

    url = "https://api.brevo.com/v3/smtp/email"
    api_key = current_app.config.get('BREVO_API_KEY')
    
    payload = {
        "sender": {
            "name": current_app.config.get('BREVO_SENDER_NAME'), 
            "email": current_app.config.get('BREVO_SENDER_EMAIL')
        },
        "to": [{"email": student_email}],
        "subject": f"PAYMENT VERIFIED: Request #{request_id}",
        "htmlContent": f"""
        <html>
        <body style="font-family: 'Segoe UI', Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
            <div style="max-width: 600px; margin: auto; background: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e0e0e0;">
                <div style="background-color: #3498db; padding: 30px; text-align: center; color: #ffffff;">
                    <div style="font-size: 48px; margin-bottom: 10px;">⚙️</div>
                    <h2 style="margin: 0; text-transform: uppercase; letter-spacing: 2px;">Payment Verified</h2>
                </div>
                <div style="padding: 30px; color: #333; line-height: 1.6;">
                    <p style="font-size: 18px; font-weight: bold;">Hello, {student_name}!</p>
                    <p>Good news! Your payment for <b>{document_name}</b> (ID: #{request_id}) has been successfully verified via PayMongo.</p>
                    
                    <div style="background-color: #e8f4fd; border-left: 5px solid #3498db; padding: 20px; margin: 20px 0; border-radius: 4px;">
                        <p style="margin: 0; color: #2c3e50;">
                            <b>Current Status:</b> Your document request is now <b>PROCESSING</b>.
                        </p>
                    </div>
                    
                    <p>Our team is now preparing your document. You will receive another notification once it is ready for pickup or delivery.</p>
                    <p style="font-size: 13px; color: #888; margin-top: 30px; text-align: center;">
                        This is an automated notification from CLAREFILES System.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
    }

    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json"
    }

    try:
        response = py_requests.post(url, json=payload, headers=headers)
        return response.status_code in [200, 201]
    except Exception as e:
        print(f"❌ Mail Error: {str(e)}")
        return False

@app.route('/webhook/paymongo', methods=['POST'])
def paymongo_webhook():
    data = request.get_json()
    print(f"DEBUG WEBHOOK FULL PAYLOAD: {data}")
    try:
        # Only process checkout_session.payment.paid (skip payment.paid to avoid duplicate)
        event_type = data.get('data', {}).get('attributes', {}).get('type', '')
        if event_type == 'payment.paid':
            print(f"DEBUG WEBHOOK: Skipping {event_type} (handled via checkout_session event)")
            return jsonify({"status": "success"}), 200
        
        attr = data.get('data', {}).get('attributes', {}).get('data', {}).get('attributes', {})
        description = attr.get('description', '')
        
        # 1. Kunin ang Request ID
        match = re.search(r'\(ID:\s*(\d+)\)', description)
        if match:
            req_id = match.group(1)
            
            # 2. Database Updates (Status and Payment Log)
            execute_query("UPDATE requests SET status = 'Processing' WHERE id = %s", (req_id,))
            
            pay_ref = data.get('data', {}).get('id')
            amt = float(attr.get('amount', 0)) / 100
            
            # Extract payment method (e.g. gcash, grab_pay, card, qrph, maya)
            payment_method = None
            try:
                # Map bank institution codes to specific e-wallet apps
                BANK_CODE_MAP = {
                    'PAPHPHM1XXX': 'maya',
                    'GCSHPHM2XXX': 'gcash',
                    'GABORPH1XXX': 'gcash',
                    'UBPHPHMMXXX': 'unionbank',
                    'BABORPH1XXX': 'bpi',
                    'ABORPH21XXX': 'rcbc',
                }
                
                # Get source from all possible paths
                source = {}
                # Path 1: payment events have source directly in attr
                if attr.get('source'):
                    source = attr.get('source', {})
                # Path 2: checkout_session payments array
                if not source:
                    payments_list = attr.get('payments', [])
                    if payments_list:
                        pm_attrs = payments_list[0].get('attributes', {})
                        source = pm_attrs.get('source', {})
                
                # Get base type (e.g. qrph, gcash, card)
                payment_method = source.get('type', None)
                
                # For QR Ph, check bank_institution_code to identify specific app
                if payment_method == 'qrph' and source.get('provider'):
                    bank_code = source['provider'].get('bank_institution_code', '')
                    print(f"DEBUG WEBHOOK: bank_institution_code = {bank_code}")
                    if bank_code in BANK_CODE_MAP:
                        payment_method = BANK_CODE_MAP[bank_code]
                
                # Fallback: checkout_session level payment_method_used
                if not payment_method:
                    payment_method = attr.get('payment_method_used', None)
                
                print(f"DEBUG WEBHOOK: payment_method = {payment_method}")
            except Exception as pm_e:
                print(f"DEBUG WEBHOOK: payment method extraction error: {pm_e}")
                payment_method = None
            
            execute_query("""
                INSERT INTO payments (request_id, reference_no, amount_paid, proof_image, payment_status, payment_method) 
                VALUES (%s, %s, %s, 'paymongo_verified.png', 'PAID', %s) 
                ON DUPLICATE KEY UPDATE 
                    reference_no = VALUES(reference_no),
                    amount_paid = VALUES(amount_paid),
                    proof_image = VALUES(proof_image),
                    payment_status = VALUES(payment_status),
                    payment_method = VALUES(payment_method)
            """, (req_id, pay_ref, amt, payment_method))

            # 3. Kumuha ng data para sa Email
            student = execute_query(
                "SELECT email, firstname, document FROM requests WHERE id = %s", 
                (req_id,), fetch_one=True
            )
            
            if student:
                # TATAWAGIN NA NATIN YUNG BAGONG FUNCTION
                success = send_payment_verified_email(
                    student['email'], 
                    student['firstname'], 
                    req_id, 
                    student['document']
                )
                
                if success:
                    print(f"✅ EMAIL SENT: Payment Verified (Processing) sent to {student['email']}")
                else:
                    print("❌ EMAIL FAILED: Check Brevo API or connection.")

        return jsonify({"status": "success"}), 200
    except Exception as e:
        print(f"🔥 ERROR: {str(e)}")
        return jsonify({"status": "error"}), 500
    
# =========================================================
# end of webhook
# =========================================================

@app.context_processor
def inject_notifications():
    # STEP 1: Mag-set ng default values para KAHIT ANONG MANGYARI, may variable ang HTML
    data = {
        'notif_count': 0,
        'pending_req_count': 0,
        'notifs': []
    }
    
    try:
        from flask import session
        
        # Get admin_id and role from session if logged in
        admin_id = session.get('admin_id')
        admin_role = session.get('admin_role')
        
        # STEP 2: Kunin ang counts mula sa notifications table
        # Unread Payments
        if admin_id:
            if admin_role == 'Super Admin':
                # Super Admin sees all notifications
                res_pay = execute_query(
                    "SELECT COUNT(*) as count FROM notifications WHERE is_read = 0 AND category = 'payment'", 
                    fetch_one=True
                )
            else:
                # Regular staff only sees their assigned notifications
                res_pay = execute_query(
                    "SELECT COUNT(*) as count FROM notifications WHERE is_read = 0 AND category = 'payment' AND (admin_id = %s OR admin_id IS NULL)", 
                    (admin_id,), fetch_one=True
                )
        else:
            res_pay = execute_query(
                "SELECT COUNT(*) as count FROM notifications WHERE is_read = 0 AND category = 'payment'", 
                fetch_one=True
            )
        if res_pay:
            data['notif_count'] = res_pay['count']

        # Unread Requests
        if admin_id:
            if admin_role == 'Super Admin':
                # Super Admin sees all notifications
                res_req = execute_query(
                    "SELECT COUNT(*) as count FROM notifications WHERE is_read = 0 AND category = 'request'", 
                    fetch_one=True
                )
            else:
                # Regular staff only sees their assigned notifications
                res_req = execute_query(
                    "SELECT COUNT(*) as count FROM notifications WHERE is_read = 0 AND category = 'request' AND (admin_id = %s OR admin_id IS NULL)", 
                    (admin_id,), fetch_one=True
                )
        else:
            res_req = execute_query(
                "SELECT COUNT(*) as count FROM notifications WHERE is_read = 0 AND category = 'request'", 
                fetch_one=True
            )
        if res_req:
            data['pending_req_count'] = res_req['count']

        # Listahan para sa Bell Dropdown
        if admin_id:
            if admin_role == 'Super Admin':
                # Super Admin sees all notifications
                res_list = execute_query(
                    "SELECT * FROM notifications ORDER BY created_at DESC LIMIT 5", 
                    fetch_all=True
                )
            else:
                # Regular staff only sees their assigned notifications
                res_list = execute_query(
                    "SELECT * FROM notifications WHERE admin_id = %s OR admin_id IS NULL ORDER BY created_at DESC LIMIT 5", 
                    (admin_id,), fetch_all=True
                )
        else:
            res_list = execute_query(
                "SELECT * FROM notifications ORDER BY created_at DESC LIMIT 5", 
                fetch_all=True
            )
        if res_list:
            data['notifs'] = res_list          

    except Exception as e:
        # Kapag may error sa SQL (halimbawa, typo), ipi-print lang sa terminal
        # pero hindi mag-e-error ang buong website (500 error)
        print(f"DEBUG: Notification Context Error -> {e}")

    # STEP 3: SIGURADUHIN na ang 'return data' ay nasa labas ng try/except 
    # at pantay sa 'data = {...}' sa itaas.
    return data

@admin_bp.app_context_processor
def inject_unread_counts():
    # Siguraduhin na 'student_messages' ang table name
    # At 'is_read = 0' para sa mga bagong messages lang
    res_messages = execute_query(
        "SELECT COUNT(*) as count FROM student_messages WHERE is_read = 0", 
        fetch_one=True
    )
    
    # Simulan sa 0 ang count
    unread_count = 0
    
    if res_messages:
        # Gagamit ng ['count'] dahil DictCursor ang gamit sa db.py
        unread_count = res_messages['count']
    
    # Ito ang gagamitin mo sa HTML: {{ unread_concerns_count }}
    return dict(unread_concerns_count=unread_count)

# =========================================================
# BLUEPRINT REGISTRATION
# =========================================================

app.register_blueprint(user_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(upload_bp)
app.register_blueprint(admin_pay_bp)

# DEBUG ROUTE - Remove after testing
@app.route('/debug/config')
def debug_config():
    return {
        'BREVO_API_KEY_SET': bool(app.config.get('BREVO_API_KEY')),
        'BREVO_API_KEY_PREVIEW': app.config.get('BREVO_API_KEY')[:30] if app.config.get('BREVO_API_KEY') else None,
        'BREVO_SENDER_EMAIL': app.config.get('BREVO_SENDER_EMAIL'),
        'BREVO_SENDER_NAME': app.config.get('BREVO_SENDER_NAME'),
    }

# =========================================================
# RUN APPLICATION
# =========================================================
try:
    with app.app_context():
        print("Initializing database tables...")
        create_tables()
        
        # 1. Fix student_info (Siguradong VARCHAR/TEXT ang birthdate)
        print("Executing birthdate column fix for student_info...")
        try:
            execute_query("ALTER TABLE student_info MODIFY COLUMN birthdate VARCHAR(255);")
            print("Birthday column fix applied successfully!")
        except Exception as sql_e:
            print(f"Note: student_info fix skipped: {sql_e}")

        # 2. Fix requests (Dagdagan at i-convert lahat ng kulang)
        print("Synchronizing requests table columns...")
        columns_to_fix = [
            ("birthdate", "VARCHAR(255)"),
            ("course_grade", "VARCHAR(255)"),
            ("year_entry", "VARCHAR(255)"),
            ("last_school", "VARCHAR(255)"),
            ("purpose", "TEXT"),
            ("address", "TEXT"),
            ("document", "VARCHAR(255)"),
            ("delivery_method", "VARCHAR(255) DEFAULT 'Pick-up'"),
            ("assigned_admin_id", "INT NULL"),
            ("updated_at", "TIMESTAMP NULL DEFAULT NULL")
        ]
        
        for col_name, col_type in columns_to_fix:
            try:
                execute_query(f"ALTER TABLE requests ADD COLUMN {col_name} {col_type};")
                execute_query(f"ALTER TABLE requests MODIFY COLUMN {col_name} {col_type};")
                print(f"Fixed/Synced column: {col_name}")
            except Exception as e:
                print(f"Note for requests ({col_name}): {e}")

        # 3. Ensure notifications schema supports role-scoped admin visibility
        print("Synchronizing notifications table columns...")
        try:
            execute_query("ALTER TABLE notifications ADD COLUMN admin_id INT NULL;")
            print("Fixed/Synced column: notifications.admin_id")
        except Exception as e:
            print(f"Note for notifications (admin_id): {e}")

        print("Database synchronization complete!")
except Exception as e:
    print(f"Database Init Error: {e}")

if __name__ == '__main__':
    create_tables() 
    
    if not os.path.exists('routes'):
        os.makedirs('routes')

    port = int(os.environ.get("PORT", 5000))
        
    app.run(host='0.0.0.0', port=port, debug=True)