from dotenv import load_dotenv
load_dotenv(override=True)
from flask import Flask
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
                execute_query(f"ALTER TABLE requests ADD COLUMN IF NOT EXISTS {col_name} {col_type};")
                execute_query(f"ALTER TABLE requests MODIFY COLUMN {col_name} {col_type};")
                print(f"Fixed/Synced column: {col_name}")
            except Exception as e:
                print(f"Note for requests ({col_name}): {e}")

        # 3. Ensure notifications schema supports role-scoped admin visibility
        print("Synchronizing notifications table columns...")
        try:
            execute_query("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS admin_id INT NULL;")
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