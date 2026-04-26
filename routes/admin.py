from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, jsonify
import secrets
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from db import execute_query 
import requests
import re
import os                          # Para sa file paths at folders
import base64                      # Para i-convert ang PDF sa format na tanggap ng Brevo API
from werkzeug.utils import secure_filename  # Para linisin ang filename at maiwasan ang security risks


# =========================================================
# BLUEPRINT INITIALIZATION
# =========================================================

# Create Blueprint for Admin Routes
admin_bp = Blueprint('admin', __name__, url_prefix='/admin') 

# =========================================================
# ADMIN HELPER FUNCTIONS 
# =========================================================

def clear_admin_session():
    """Remove all admin-related session keys."""
    session.pop('admin_id', None)
    session.pop('admin_email', None)
    session.pop('admin_role', None)
    session.pop('admin_fullname', None)
    session.pop('admin_authenticated', None)

def admin_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin_id = session.get('admin_id')
        admin_role = session.get('admin_role')
        admin_authenticated = session.get('admin_authenticated')

        # Prevent student/user sessions from traversing admin-protected endpoints.
        if session.get('user_email') and admin_authenticated is not True:
            clear_admin_session()
            flash("Admin access is restricted to authorized admin accounts.", "warning")
            return redirect(url_for('user.dashboard'))

        # Block stale or partially populated sessions (including old cookies without auth flag).
        if not admin_id or not admin_role or admin_authenticated is not True:
            clear_admin_session()
            flash("Please log in to access the Admin Panel.", "warning")
            return redirect(url_for('admin.login'))

        # Validate that the admin account still exists and is active.
        admin_user = execute_query(
            "SELECT id, email, role_access, status FROM admin_users WHERE id = %s",
            (admin_id,),
            fetch_one=True
        )
        if (
            not admin_user
            or admin_user.get('status') != 'Active'
            or admin_user.get('email') != session.get('admin_email')
        ):
            clear_admin_session()
            flash("Your admin session is no longer valid. Please log in again.", "warning")
            return redirect(url_for('admin.login'))

        # Keep role in sync if changed in DB after login.
        if admin_user.get('role_access') and admin_user['role_access'] != admin_role:
            session['admin_role'] = admin_user['role_access']

        return f(*args, **kwargs)
    return decorated_function

# ---------------------------------------------------------
# EMAIL FUNCTION REPLACED AND FIXED TO WORK WITH BLUEPRINT
# ---------------------------------------------------------
# ---------------------------------------------------------
# EMAIL FUNCTION WITH PDF ATTACHMENT SUPPORT (BREVO API)
# ---------------------------------------------------------
def send_status_update_email(request_data, new_status, attachment_path=None):
    """
    Sends a status update email via Brevo API.
    Supports optional PDF attachments for 'Completed' requests.
    """
    # 1. API CONFIGURATION
    url = "https://api.brevo.com/v3/smtp/email"
    api_key = current_app.config.get('BREVO_API_KEY')
    sender_email = current_app.config.get('BREVO_SENDER_EMAIL')
    sender_name = current_app.config.get('BREVO_SENDER_NAME')

    if not api_key:
        print("ERROR: BREVO_API_KEY is missing in config.")
        return False
    if not sender_email:
        print("ERROR: BREVO_SENDER_EMAIL is missing in config.")
        return False
        
    recipient_email = request_data.get('requester_email')
    request_id = request_data.get('id')
    document = request_data.get('document')
    final_price = float(request_data.get('final_price', 0.0))
    
    subject = f"UPDATE: Your Document Request (#{request_id}) Status"
    
    # 2. TUKUYIN ANG KULAY AT ICON BASE SA STATUS
    status_config = {
        'Accepted': {'bg': '#2cc5ad', 'icon': '✅', 'title': 'REQUEST APPROVED'},
        'Processing': {'bg': '#3498db', 'icon': '⚙️', 'title': 'PAYMENT VERIFIED'},
        'Ready for pickup': {'bg': '#f1c40f', 'icon': '📦', 'title': 'READY FOR PICK-UP'},
        'Ready for delivery': {'bg': '#e67e22', 'icon': '🚚', 'title': 'READY FOR DELIVERY'},
        'Rejected': {'bg': '#e74c3c', 'icon': '❌', 'title': 'REQUEST REJECTED'},
        'Completed': {'bg': '#2ecc71', 'icon': '🎉', 'title': 'REQUEST COMPLETED'},
    }

    # Default values kung wala sa listahan ang status
    config = status_config.get(new_status, {'bg': '#0f111a', 'icon': '🔔', 'title': 'STATUS UPDATE'})

    # 3. AYUSIN ANG TEXT CONTENT BASE SA STATUS
    if new_status == 'Accepted':
        status_message = f"Your request for <b>{document}</b> (ID: #{request_id}) has been <b>APPROVED</b>!"
        sub_message = f"<b>Fee Details:</b> PHP {final_price:.2f}<br>Please visit the 'Payments' section on your portal to proceed with the payment."
    
    elif new_status == 'Processing':
        status_message = f"Your payment for <b>{document}</b> (ID: #{request_id}) has been <b>VERIFIED</b>."
        sub_message = "Your request is now being processed by our team. Please wait for another notification once it is ready. "

    elif new_status == 'Ready for pickup':
        pickup_msg = request_data.get('pickup_message', '').strip()
        status_message = f"Good news! Your request for <b>{document}</b> (ID: #{request_id}) is now <b>READY FOR PICK-UP</b>."
        sub_message = "You may now visit the designated office to claim your document every Saturday. Please bring a valid ID."
        if pickup_msg:
            sub_message += "<br><br>"
            for part in pickup_msg.split(' | '):
                sub_message += f"<b>{part.split(': ', 1)[0]}:</b> {part.split(': ', 1)[1] if ': ' in part else part}<br>"
            
    elif new_status == 'Ready for delivery':
        pickup_msg = request_data.get('pickup_message', '').strip()
        contact = request_data.get('contact', 'your registered number')
        status_message = f"Your request for <b>{document}</b> (ID: #{request_id}) is now <b>READY FOR DELIVERY</b>."
        sub_message = f"Please wait for our courier to contact you at <b>{contact}</b> for the delivery schedule."
        # if pickup_msg:
        #     sub_message += f"<br><br><b>DATE & TIME:</b> {pickup_msg}"

    elif new_status == 'Rejected':
        reason = request_data.get('rejection_reason', 'Incomplete requirements or invalid information.')
        status_message = f"We regret to inform you that your request for <b>{document}</b> (ID: #{request_id}) has been <b>REJECTED</b>."
        sub_message = f"<b>REASON:</b> {reason}"

    elif new_status == 'Completed':
        status_message = f"Your request for <b>{document}</b> (ID: #{request_id}) is now <b>COMPLETED</b>."
        sub_message = "Thank you for using the CLAREFILES Document Request System! We hope we served you well. Attached below is the digital copy of your document."
    
    else:
        status_message = f"Your request status for <b>{document}</b> has been updated to: <b>{new_status}</b>."
        sub_message = "Please log in to your portal for more details."

    # 4. HTML EMAIL TEMPLATE
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="margin: 0; padding: 0; font-family: 'Segoe UI', Arial, sans-serif; background-color: #f4f4f4;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
            <tr>
                <td align="center" style="padding: 20px 0;">
                    <table width="600" cellspacing="0" cellpadding="0" border="0" style="background-color: #ffffff; border-radius: 15px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
                        <tr>
                            <td align="center" style="background-color: {config['bg']}; padding: 40px 20px;">
                                <div style="font-size: 50px; margin-bottom: 10px;">{config['icon']}</div>
                                <h2 style="color: #ffffff; margin: 0; text-transform: uppercase; letter-spacing: 2px; font-size: 24px;">{config['title']}</h2>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 40px 30px; text-align: center; color: #333333; line-height: 1.6;">
                                <p style="font-size: 18px; font-weight: bold; margin-bottom: 20px;">Hello!</p>
                                <p style="font-size: 16px; margin-bottom: 25px; color: #444;">{status_message}</p>
                                <div style="background-color: #f9f9f9; border-left: 5px solid {config['bg']}; padding: 25px; text-align: left; margin: 25px 0; border-radius: 8px;">
                                    <p style="margin: 0; font-size: 15px; color: #555;">{sub_message}</p>
                                </div>
                                <p style="font-size: 13px; color: #888; margin-top: 35px;">
                                    <strong>NOTE:</strong> Track your progress anytime via the account portal. Documents are ready within 1–2 business weeks and are available for pickup exclusively on the Saturday of their release.
                                </p>
                            </td>
                        </tr>
                        <tr>
                            <td align="center" style="background-color: #0f111a; padding: 30px 20px; color: #ffffff; font-size: 12px;">
                                <p style="margin: 0; font-weight: bold; font-size: 14px; letter-spacing: 1px;">CLAREFILES SYSTEM</p>
                                <p style="margin: 8px 0 0 0; opacity: 0.6;">This is an automated notification. Please do not reply directly to this email.</p>
                                <p style="margin: 15px 0 0 0; opacity: 0.4;">&copy; 2026 Document Request System</p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    # 5. PREPARE PAYLOAD
    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": recipient_email}],
        "subject": subject,
        "htmlContent": html_body
    }

    # --- NEW: ATTACHMENT LOGIC ---
    if attachment_path and os.path.exists(attachment_path):
        try:
            with open(attachment_path, "rb") as f:
                # Encode the PDF content to Base64
                b64_content = base64.b64encode(f.read()).decode('utf-8')
            
            # Add attachment to payload
            payload["attachment"] = [{
                "content": b64_content,
                "name": os.path.basename(attachment_path)
            }]
        except Exception as file_err:
            print(f"⚠️ Error encoding attachment: {file_err}")

    # 6. BREVO API CALL
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code in [200, 201]:
            print(f"Status email (with attachment if any) sent to {recipient_email}")
            return True
        else:
            print(f"❌ Brevo Error: {response.text}")
            return False
    except Exception as e:
        print(f"⚠️ Connection Error: {e}")
        return False
# ---------------------------------------------------------
# END: EMAIL FUNCTION FIX
# ---------------------------------------------------------

def get_document_types():
    """Retrieving the list of available documents and fees."""
    query = "SELECT * FROM document_types ORDER BY doc_name"
    return execute_query(query, fetch_all=True)


def record_request_history(request_id, status, admin_id=None):
    """Store every status change timestamp for auditing and history display."""
    try:
        execute_query(
            'INSERT INTO request_history (request_id, admin_id, status) VALUES (%s, %s, %s)',
            (request_id, admin_id, status)
        )
    except Exception as e:
        print(f"Request history insert failed: {e}")


# =========================================================
# NEW DEDICATED REQUEST FLOW ROUTE (AUTO-PRICE & REJECTION)
# =========================================================
@admin_bp.route('/update-request-flow/<int:req_id>', methods=['POST'])
@admin_login_required
def update_request_flow(req_id):
    action = request.form.get('action')
    new_status = request.form.get('new_status')
    manual_price = request.form.get('manual_price')

    req_data = execute_query('''
        SELECT r.*, d.fee 
        FROM requests r 
        LEFT JOIN document_types d ON r.document = d.doc_name 
        WHERE r.id = %s
    ''', (req_id,), fetch_one=True)

    if not req_data:
        flash("Request not found.", "danger")
        return redirect(request.referrer)

    if action == 'update':
        file_path = None
        
        # Pag-handle ng PDF File Upload
        if new_status == 'Completed' and 'document_file' in request.files:
            file = request.files['document_file']
            if file and file.filename != '':
                filename = secure_filename(f"COMPLETE_{req_id}_{file.filename}")
                upload_folder = os.path.join(current_app.static_folder, 'uploads/completed_docs')
                
                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)
                
                file_path = os.path.join(upload_folder, filename)
                file.save(file_path)

        # Database Updates
        if new_status == 'Accepted':
            final_to_save = float(manual_price) if manual_price and float(manual_price) > 0 else (req_data['fee'] or 0.0)

            admin_id = session.get('admin_id')  # 🔥 get logged-in admin

            execute_query(
                'UPDATE requests SET status = %s, final_price = %s, assigned_admin_id = %s, updated_at = NOW() WHERE id = %s',
                ('Accepted', final_to_save, admin_id, req_id)
            )

            record_request_history(req_id, 'Accepted', admin_id)
            req_data['final_price'] = final_to_save
        else:
            admin_id = session.get('admin_id')
            if new_status == 'Completed':
                verif_token = secrets.token_urlsafe(24)
                rel_path = ('uploads/completed_docs/' + os.path.basename(file_path)) if file_path else None
                execute_query(
                    'UPDATE requests SET status = %s, assigned_admin_id = %s, updated_at = NOW(), document_file_path = COALESCE(%s, document_file_path), verification_token = %s WHERE id = %s',
                    (new_status, admin_id, rel_path, verif_token, req_id)
                )
            elif file_path:
                rel_path = 'uploads/completed_docs/' + os.path.basename(file_path)
                execute_query(
                    'UPDATE requests SET status = %s, assigned_admin_id = %s, updated_at = NOW(), document_file_path = %s WHERE id = %s',
                    (new_status, admin_id, rel_path, req_id)
                )
            elif new_status == 'Rejected':
                rejection_reason = request.form.get('rejection_reason', 'Incomplete requirements or invalid information.')
                execute_query('UPDATE requests SET status = %s, assigned_admin_id = %s, updated_at = NOW(), rejection_reason = %s WHERE id = %s', (new_status, admin_id, rejection_reason, req_id))
            else:
                execute_query('UPDATE requests SET status = %s, assigned_admin_id = %s, updated_at = NOW() WHERE id = %s', (new_status, admin_id, req_id))
            record_request_history(req_id, new_status, admin_id)

        # Email Notification (Passing attachment_path)
        email_payload = dict(req_data)
        # Add rejection reason if status is Rejected
        if new_status == 'Rejected':
            rejection_reason = request.form.get('rejection_reason', 'Incomplete requirements or invalid information.')
            email_payload['rejection_reason'] = rejection_reason
        # Add pickup message if status is Ready for pickup/delivery
        if new_status in ('Ready for pickup', 'Ready for delivery'):
            email_payload['pickup_message'] = request.form.get('pickup_message', '')
        send_status_update_email(email_payload, new_status, attachment_path=file_path)
        
        flash(f"Request #{req_id} updated and notification sent.", "success")

    elif action == 'delete':
        execute_query('DELETE FROM requests WHERE id = %s', (req_id,))
        flash(f"Request #{req_id} deleted.", "info")

    return redirect(request.referrer)

# =========================================================
# NEW: SEPARATE DASHBOARD ROUTE
# =========================================================

@admin_bp.route('/overview', methods=['GET', 'POST'])
@admin_login_required
def overview():
    # ==========================================
    # 1. POST HANDLER (Para sa Update at Delete)
    # ==========================================
    if request.method == 'POST':
        action = request.form.get('action')
        request_id = request.form.get('request_id')

        if action == 'update_status' and request_id:
            new_status = request.form.get('new_status')
            # Kunin ang data para sa email bago i-update
            current_request = execute_query('SELECT * FROM requests WHERE id = %s', (request_id,), fetch_one=True)
            admin_id = session.get('admin_id')
            if new_status == 'Rejected':
                rejection_reason = request.form.get('rejection_reason', 'Incomplete requirements or invalid information.')
                execute_query('UPDATE requests SET status = %s, assigned_admin_id = %s, updated_at = NOW(), rejection_reason = %s WHERE id = %s', (new_status, admin_id, rejection_reason, request_id))
            else:
                execute_query('UPDATE requests SET status = %s, assigned_admin_id = %s, updated_at = NOW() WHERE id = %s', (new_status, admin_id, request_id))
            record_request_history(request_id, new_status, admin_id)

            # Send Email Notification
            if current_request:
                # Add rejection reason if status is Rejected
                if new_status == 'Rejected':
                    current_request['rejection_reason'] = rejection_reason
                # Add pickup message if status is Ready for pickup/delivery
                if new_status in ('Ready for pickup', 'Ready for delivery'):
                    current_request['pickup_message'] = request.form.get('pickup_message', '')
                send_status_update_email(current_request, new_status)
                flash(f"Request #{request_id} updated to {new_status}.", "success")

        elif action == 'delete_req' and request_id:
            execute_query('DELETE FROM requests WHERE id = %s', (request_id,))
            flash(f"Request #{request_id} has been permanently deleted.", "danger")
            
        return redirect(url_for('admin.overview'))

    # ==========================================
    # 2. GET HANDLER (Para sa Charts at Table)
    # ==========================================

    context = {'menu_type': 'overview'}
    
    admin_id = session.get('admin_id')
    admin_role = session.get('admin_role')
    
    # Role-based filter for analytics
    role_filter = ""
    if admin_role != 'Super Admin':
        role_filter = f"WHERE assigned_admin_id = {admin_id}"
    
    # 1. Summary Cards Data
    stats_query = f"""
        SELECT 
    COUNT(*) as total,
        SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) as completed,
        SUM(CASE WHEN status = 'Rejected' THEN 1 ELSE 0 END) as rejected,
        SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END) as pending,
        SUM(CASE WHEN status = 'Accepted' THEN 1 ELSE 0 END) as verified,
        SUM(CASE WHEN status = 'Processing' THEN 1 ELSE 0 END) as processing,
        SUM(CASE WHEN status = 'Ready for pickup' THEN 1 ELSE 0 END) as ready,
        SUM(CASE WHEN status = 'Ready for delivery' THEN 1 ELSE 0 END) as readydelivery
    FROM requests
    {role_filter}
    """
    stats_result = execute_query(stats_query, fetch_one=True)
    context['stats'] = stats_result if stats_result else {'total':0, 'pending':0,'completed':0,'rejected':0, 'verified':0,'processing':0,'readydelivery':0, 'ready':0}

    # 2. Pie Chart Data
    pie_query = f"SELECT status, COUNT(*) as count FROM requests {role_filter} GROUP BY status"
    pie_results = execute_query(pie_query, fetch_all=True)
    context['pie_labels'] = [r['status'] for r in pie_results or []]
    context['pie_counts'] = [r['count'] for r in pie_results or []]

    # 3. Bar Chart Data (Monthly Volume)
    # Kunin lang ang summary counts per month para sa current year
    where_clause = "WHERE timestamp >= DATE_SUB(CURDATE(), INTERVAL 1 YEAR)"
    if admin_role != 'Super Admin':
        where_clause += f" AND assigned_admin_id = {admin_id}"
    
    bar_query = f"""
    SELECT 
    DATE_FORMAT(timestamp, '%b') as month,
    COUNT(id) as count
        FROM requests
        {where_clause}
        GROUP BY DATE_FORMAT(timestamp, '%Y-%m'), DATE_FORMAT(timestamp, '%b')
        ORDER BY DATE_FORMAT(timestamp, '%Y-%m')
    """
    bar_results = execute_query(bar_query, fetch_all=True)
    context['bar_labels'] = [r['month'] for r in bar_results or []]
    context['bar_counts'] = [r['count'] for r in bar_results or []]

# D. All Requests Data (Para sa Table sa baba)
    # Walang LIMIT para lumabas lahat ng requests
    requests_where = ""
    if admin_role != 'Super Admin':
        requests_where = f"WHERE r.assigned_admin_id = {admin_id}"
    
    context['requests'] = execute_query(f"""
        SELECT r.*, s.firstname AS student_firstname, s.lastname AS student_lastname,
               a.fullname AS admin_fullname, a.email AS admin_email
        FROM requests r
        LEFT JOIN student_info s ON r.requester_email = s.requester_email
        LEFT JOIN admin_users a ON r.assigned_admin_id = a.id
        {requests_where}
        ORDER BY r.id DESC
    """, fetch_all=True)

    context['requests'] = context['requests'] if context['requests'] else []

    request_ids = [req['id'] for req in context['requests']] if context['requests'] else []
    if request_ids:
        placeholders = ','.join(['%s'] * len(request_ids))
        history_rows = execute_query(
            f"SELECT request_id, status, timestamp FROM request_history WHERE request_id IN ({placeholders}) ORDER BY timestamp ASC",
            tuple(request_ids),
            fetch_all=True
        )
        history_map = {}
        for row in history_rows or []:
            history_map.setdefault(row['request_id'], []).append(row)
        for req in context['requests']:
            req['history'] = history_map.get(req['id'], [])
    else:
        for req in context['requests']:
            req['history'] = []

    if admin_role == 'Record Staff':
        context['recent_moves'] = execute_query(
            '''
            SELECT id, document, status, updated_at, timestamp
            FROM requests
            WHERE assigned_admin_id = %s
            ORDER BY COALESCE(updated_at, timestamp) DESC
            LIMIT 5
            ''',
            (admin_id,),
            fetch_all=True
        )
    
    # 5. Staff Analytics Data (Only for Super Admin)
    if admin_role == 'Super Admin':
        staff_analytics_query = """
            SELECT
                a.id,
                a.fullname,
                a.email,
                a.role_access,
                COUNT(r.id) as total_requests,
                SUM(CASE WHEN r.status = 'Accepted' THEN 1 ELSE 0 END) as accepted_requests,
                SUM(CASE WHEN r.status = 'Completed' THEN 1 ELSE 0 END) as completed_requests,
                SUM(CASE WHEN r.status = 'Rejected' THEN 1 ELSE 0 END) as rejected_requests,
                SUM(CASE WHEN r.status = 'Processing' THEN 1 ELSE 0 END) as processing_requests,
                SUM(CASE WHEN r.status = 'Ready for pickup' THEN 1 ELSE 0 END) as ready_pickup,
                SUM(CASE WHEN r.status = 'Ready for delivery' THEN 1 ELSE 0 END) as ready_delivery,
                AVG(CASE WHEN r.final_price > 0 THEN r.final_price ELSE NULL END) as avg_request_value,
                MAX(r.timestamp) as last_activity,
                MAX(CASE WHEN r.status = 'Accepted' THEN r.timestamp END) as last_accepted,
                MAX(CASE WHEN r.status = 'Completed' THEN r.timestamp END) as last_completed,
                MAX(CASE WHEN r.status = 'Rejected' THEN r.timestamp END) as last_rejected,
                MAX(CASE WHEN r.status = 'Processing' THEN r.timestamp END) as last_processed
            FROM admin_users a
            LEFT JOIN requests r ON a.id = r.assigned_admin_id
            WHERE a.status = 'Active' AND a.role_access != 'Super Admin'
            GROUP BY a.id, a.fullname, a.email, a.role_access
            ORDER BY (SUM(CASE WHEN r.status = 'Accepted' THEN 1 ELSE 0 END) + SUM(CASE WHEN r.status = 'Completed' THEN 1 ELSE 0 END)) DESC, COUNT(r.id) DESC
        """
        staff_data = execute_query(staff_analytics_query, fetch_all=True)
        context['staff_analytics'] = staff_data
        
        # Calculate summary statistics
        if staff_data:
            total_staff = len(staff_data)
            active_staff = len([s for s in staff_data if s['total_requests'] > 0])
            total_accepted = sum(s['accepted_requests'] or 0 for s in staff_data)
            total_completed = sum(s['completed_requests'] or 0 for s in staff_data)
            total_requests = sum(s['total_requests'] or 0 for s in staff_data)
            
            avg_success_rate = 0
            if total_requests > 0:
                avg_success_rate = ((total_accepted + total_completed) / total_requests) * 100
            
            context.update({
                'total_staff': total_staff,
                'active_staff': active_staff,
                'total_accepted': total_accepted,
                'total_completed': total_completed,
                'avg_success_rate': avg_success_rate
            })
    
    # Add role info for template conditional display
    context['admin_role'] = admin_role

    return render_template('admin_dashboard.html', **context)
# =========================================================
# ADMIN ROUTES
# =========================================================

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_email') and session.get('admin_authenticated') is not True:
        return redirect(url_for('user.dashboard'))

    if session.get('admin_id') and session.get('admin_authenticated') is True:
        return redirect(url_for('admin.default')) 
    if session.get('admin_id') and session.get('admin_authenticated') is not True:
        clear_admin_session()
    
    if request.method == 'POST':
        # These variables are ONLY created during a POST (when you click submit)
        email = request.form.get('email', '').strip()
        password = request.form.get('password')
        
        print(f"--- LOGIN ATTEMPT ---")
        print(f"Typed Email: '{email}'")
        print(f"SESSION FULLNAME:", session.get('admin_fullname'))
        
        admin_user = execute_query("SELECT id, email, password_hash, fullname, role_access, status FROM admin_users WHERE email = %s", (email,), fetch_one=True)
        
        if admin_user:
            print(f"User found in DB. Status is: {admin_user['status']}")
            
            if admin_user['status'] != 'Active':
                flash("Account is inactive.", "danger")
            elif check_password_hash(admin_user['password_hash'], password):
                print("Password Match! Logging in...")

                # Isolate user/admin sessions to avoid cross-role session carryover.
                session.pop('user_email', None)
                session.pop('temp_email', None)
                session.pop('otp_code', None)
                session.pop('otp_expiry', None)
                session.pop('otp_requested_at', None)

                session['admin_id'] = admin_user['id']
                session['admin_email'] = admin_user['email']
                session['admin_role'] = admin_user['role_access']
                session['admin_fullname'] = admin_user['fullname']
                session['admin_authenticated'] = True
                flash(f"Welcome back, {admin_user['fullname']}!", "success")
                return redirect(url_for('admin.default'))
            else:
                print("Password FAIL: Hash did not match.")
                flash("Invalid email or password.", "danger")
        else:
            print("Email FAIL: No user found with that email.")
            flash("Invalid email or password.", "danger")
            
    # This part runs for GET requests (loading the page)
    return render_template('admin_login.html' )

@admin_bp.route('/logout')
def admin_logout():
    clear_admin_session()
    flash("You have been logged out.", "info")
    return redirect(url_for('admin.login'))

@admin_bp.route('/', endpoint='default')
@admin_login_required
def admin_default():
    return redirect(url_for('admin.admin', menu_type='overview'))



@admin_bp.route('/<menu_type>', methods=['GET', 'POST'])
@admin_login_required
def admin(menu_type):
    context = {'menu_type': menu_type}
    
    
    # [REQUESTS MANAGEMENT]
    if menu_type in ['overview', 'pending_requests', 'all_requests', 'approved', 'rejected', 'completed', 'ready_for_pickup','ready_for_delivery','processing', 'pending']:
        
        status_filter = "1=1"
        if menu_type == 'pending_requests' or menu_type == 'pending': status_filter = "r.status = 'Pending'"
        elif menu_type == 'approved': status_filter = "r.status = 'Accepted'"
        elif menu_type == 'rejected': status_filter = "r.status = 'Rejected'"
        elif menu_type == 'ready_for_pickup': status_filter = "r.status = 'Ready for pickup'"
        elif menu_type == 'ready_for_delivery': status_filter = "r.status = 'Ready for delivery'"
        elif menu_type == 'processing': status_filter = "r.status = 'Processing'"
        elif menu_type == 'completed': status_filter = "r.status = 'Completed'"
        elif menu_type == 'overview': status_filter = "r.status NOT IN ('Rejected', 'Completed')" 

        if request.method == 'POST':
            action = request.form.get('action')
            request_id = request.form.get('request_id')

            if action == 'update_status' and request_id:
                new_status = request.form.get('new_status')
                final_price = request.form.get('final_price', '0.0')

                current_request = execute_query('SELECT * FROM requests WHERE id = %s', (request_id,), fetch_one=True)
                
                # Perform Update Logic
                if new_status == 'Accepted':
                    try:
                        final_price = float(final_price)
                    except ValueError:
                        final_price = 0.0
                    
                    admin_id = session.get('admin_id')  # ✅ correct
                
                    print("SESSION:", session)
                    print("ADMIN ID:", session.get('admin_id'))
                    

                    update_query = '''
                        UPDATE requests 
                        SET status = %s, final_price = %s, assigned_admin_id = %s, updated_at = NOW()
                        WHERE id = %s
                    '''

                    execute_query(update_query, ('Accepted', final_price, admin_id, request_id))
                    record_request_history(request_id, 'Accepted', admin_id)

                else:
                    admin_id = session.get('admin_id')
                    if new_status == 'Rejected':
                        rejection_reason = request.form.get('rejection_reason', 'Incomplete requirements or invalid information.')
                        execute_query('UPDATE requests SET status = %s, assigned_admin_id = %s, updated_at = NOW(), rejection_reason = %s WHERE id = %s', (new_status, admin_id, rejection_reason, request_id))
                    else:
                        execute_query('UPDATE requests SET status = %s, assigned_admin_id = %s, updated_at = NOW() WHERE id = %s', (new_status, admin_id, request_id))
                    record_request_history(request_id, new_status, admin_id)

                # Send Email Notification 
                if current_request:
                    # Add rejection reason if status is Rejected
                    if new_status == 'Rejected':
                        current_request['rejection_reason'] = rejection_reason
                    # Add pickup message if status is Ready for pickup/delivery
                    if new_status in ('Ready for pickup', 'Ready for delivery'):
                        current_request['pickup_message'] = request.form.get('pickup_message', '')
                    send_status_update_email(current_request, new_status)
                    flash(f"Status for Request #{request_id} updated to {new_status} and notification sent.", "success")
            
            elif action == 'delete_req' and request_id:
                 execute_query('DELETE FROM requests WHERE id = %s', (request_id,))
                 flash(f"Request #{request_id} successfully deleted.", "success")
            
            return redirect(url_for('admin.admin', menu_type=menu_type))


        # [QUERY]
        admin_id = session.get('admin_id')
        admin_role = session.get('admin_role')

        # Base condition
        extra_filter = ""

        # Apply role-based filtering
        if admin_role != 'Super Admin':
            extra_filter = "AND (r.assigned_admin_id = %s OR r.assigned_admin_id IS NULL)"

        query = f'''
            SELECT r.*, 
                s.middlename, s.suffix, s.age, s.last_school AS student_last_school, 
                s.enrollment_status, s.course_grade AS student_course_grade, 
                s.student_id, s.address AS student_address,
                s.contact AS student_contact, s.birthdate AS student_birthdate, 
                s.lastname AS student_lastname, s.firstname AS student_firstname,
                a.fullname AS admin_fullname, a.email AS admin_email, a.role_access AS admin_role
            FROM requests r 
            LEFT JOIN student_info s ON r.requester_email = s.requester_email
            LEFT JOIN admin_users a ON r.assigned_admin_id = a.id
            WHERE {status_filter}
            {extra_filter}
            ORDER BY r.id DESC
        '''

        # Execute properly depending on role
        if admin_role == 'Super Admin':
            requests_data = execute_query(query, fetch_all=True)
        else:
            requests_data = execute_query(query, (admin_id,), fetch_all=True)

        context['requests'] = requests_data
        
        context['status_options'] = ['Pending','Processing', 'Accepted', 'Ready for pickup', 'Rejected', 'Completed']

        
    

    # [DOCUMENTS MANAGEMENT]
    elif menu_type in ['manage_docs', 'set_fees']:
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'add_doc':
                doc_name = request.form.get('doc_name')
                fee = float(request.form.get('fee', 0.0))
                education_level = request.form.get('education_level', 'All')
                query = 'INSERT IGNORE INTO document_types (doc_name, fee, education_level) VALUES (%s, %s, %s)'
                execute_query(query, (doc_name, fee, education_level))
                flash(f"Document {doc_name} added/updated.", "success")
            elif action == 'update_fee':
                doc_id = request.form.get('doc_id')
                new_fee = float(request.form.get('new_fee', 0.0))
                execute_query('UPDATE document_types SET fee = %s WHERE id = %s', (new_fee, doc_id))
                flash(f"Fee updated for Document ID {doc_id}.", "success")
            elif action == 'update_level':
                doc_id = request.form.get('doc_id')
                new_level = request.form.get('new_level', 'All')
                execute_query('UPDATE document_types SET education_level = %s WHERE id = %s', (new_level, doc_id))
                flash(f"Education level updated for Document ID {doc_id}.", "success")
            elif action == 'delete_doc':
                doc_id = request.form.get('doc_id')
                execute_query('DELETE FROM document_types WHERE id = %s', (doc_id,))
                flash(f"Document ID {doc_id} deleted.", "success")
            
            return redirect(url_for('admin.admin', menu_type=menu_type))

        context['documents'] = get_document_types()
   
    

    # [REPORTS / NOTIFICATIONS / SETTINGS] 
    
        
    return render_template('admin.html', **context)

@admin_bp.route('/api/status-counts')
@admin_login_required
def api_status_counts():
    admin_id = session.get('admin_id')
    admin_role = session.get('admin_role')
    status_map = {
        'all_requests': "1=1",
        'pending_requests': "r.status = 'Pending'",
        'approved': "r.status = 'Accepted'",
        'rejected': "r.status = 'Rejected'",
        'processing': "r.status = 'Processing'",
        'ready_for_pickup': "r.status = 'Ready for pickup'",
        'ready_for_delivery': "r.status = 'Ready for delivery'",
        'completed': "r.status = 'Completed'",
    }
    counts = {}
    for key, where in status_map.items():
        if admin_role == 'Super Admin':
            row = execute_query(f"SELECT COUNT(*) as cnt FROM requests r WHERE {where}", fetch_one=True)
        else:
            row = execute_query(
                f"SELECT COUNT(*) as cnt FROM requests r WHERE {where} AND (r.assigned_admin_id = %s OR r.assigned_admin_id IS NULL)",
                (admin_id,), fetch_one=True
            )
        counts[key] = row['cnt'] if row else 0
    return jsonify(counts)


@admin_bp.route('/admin/reports')
@admin_login_required
def admin_reports():
    if session.get('admin_role') not in ['Super Admin']:
        flash("You do not have permission to access this page.", "danger")
        return redirect(url_for('admin.admin_manage_accounts'))
    try:   
        # --- 1. Summary Stats ---
        # Kunin ang total students
        total_students_res = execute_query("SELECT COUNT(*) as count FROM users", fetch_one=True)
         
        # FIX: 'PAID' ang status para mag-match sa admin_payments.py
        # Ginamit ang COALESCE para sigurado na 0 ang babalik kung walang records
        revenue_query = "SELECT COALESCE(SUM(amount_paid), 0) as total FROM payments WHERE payment_status = 'PAID'"
        revenue_res = execute_query(revenue_query, fetch_one=True)
        
        requests_total_res = execute_query("SELECT COUNT(*) as total FROM requests", fetch_one=True)
        # Inbox/Message stats
        message_stats_res = execute_query("SELECT COUNT(*) as total FROM student_messages", fetch_one=True)

        paid_count_res = execute_query("SELECT COUNT(*) as count FROM payments WHERE payment_status = 'PAID'", fetch_one=True)
        approved_count = paid_count_res['count'] if paid_count_res else 0
        
        # Request counts
        stats_query = """
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN status = 'Pending' THEN 1 ELSE 0 END) as pending,
                   SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) as completed
            FROM requests
        """
        stats_result = execute_query(stats_query, fetch_one=True)

        # --- 2. Chart Data (Monthly Volume para sa Bar Chart) ---
        bar_query = """
            SELECT DATE_FORMAT(timestamp, '%b') as month, COUNT(id) as count 
            FROM requests 
            GROUP BY DATE_FORMAT(timestamp, '%Y-%m'), DATE_FORMAT(timestamp, '%b')
            ORDER BY DATE_FORMAT(timestamp, '%Y-%m')
        """
        bar_results = execute_query(bar_query, fetch_all=True)

        # --- 3. Pie Chart Data (Status Breakdown) ---
        pie_query = "SELECT status, COUNT(*) as count FROM requests GROUP BY status"
        pie_results = execute_query(pie_query, fetch_all=True)

        # --- 4. I-package ang lahat ng data sa 'reports_data' ---
        # Dito natin sinisiguro na lahat ng variable ay may laman bago ipasa sa HTML
        reports_data = {
            'revenue': float(revenue_res['total']) if revenue_res else 0.0,
            'students': total_students_res['count'] if total_students_res else 0,
            'requests_total': requests_total_res['total'] if requests_total_res else 0,
            'requests_pending': stats_result['pending'] if stats_result else 0,
            'messages': message_stats_res['total'] if message_stats_res else 0,
            'approved_payments': approved_count
        }

        return render_template('admin_reports.html', 
                               reports=reports_data,
                               bar_labels=[r['month'] for r in bar_results or []],
                               bar_counts=[r['count'] for r in bar_results or []],
                               pie_labels=[r['status'] for r in pie_results or []],
                               pie_counts=[r['count'] for r in pie_results or []],
                               active_page='reports')

    except Exception as e:
        print(f"Error in admin_reports: {e}")
        flash("An error occurred while loading the reports.", "danger")
        return redirect(url_for('admin.admin'))

@admin_bp.route('/students/list', methods=['GET'])
@admin_login_required
def student_list_view():
    # Inayos ko ang query para sigurado ang pagkuha ng status at pag-sort
    query = '''
        SELECT 
            u.email, 
            COALESCE(u.status, 'Active') AS account_status,
            s.lastname, 
            s.firstname, 
            s.middlename, 
            s.suffix, 
            s.gender,
            s.age, 
            s.contact, 
            s.birthdate, 
            s.enrollment_status, 
            s.course_grade, 
            s.student_id,
            s.address
        FROM users u 
        LEFT JOIN student_info s ON u.email = s.requester_email 
        WHERE u.role != 'admin'
        ORDER BY u.id DESC
    '''
    
    try:
        # fetch_all=True dahil DictCursor ang gamit mo sa db.py
        result = execute_query(query, fetch_all=True)
        
        # DEBUG: Tingnan sa terminal (itim na window)
        print(f"DEBUG: Found {len(result) if result else 0} students.")
        
        # Siguraduhin na list ang ipapasa sa HTML
        users_data = result if result else []
        
    except Exception as e:
        print(f"SQL Error in student_list_view: {e}")
        users_data = []

    return render_template('admin_student_list.html', users=users_data)

@admin_bp.route('/toggle_user_status', methods=['POST'])
@admin_login_required
def toggle_user_status():
    email = request.form.get('user_email')
    
    # Kukunin ang current status
    user = execute_query("SELECT status FROM users WHERE email = %s", (email,), fetch_one=True)
    
    if user:
        new_status = 'Blocked' if user['status'] == 'Active' else 'Active'
        execute_query("UPDATE users SET status = %s WHERE email = %s", (new_status, email))
        flash(f"User {email} has been {new_status.lower()} successfully!", "success")
    
    return redirect(url_for('admin.student_list_view'))
# [ADMIN ACCOUNT MANAGEMENT]

@admin_bp.route('/manage-accounts', methods=['GET'], endpoint='admin_manage_accounts')
@admin_login_required
def admin_manage_accounts():
    query = "SELECT id, fullname, email, role_access, date_created, status FROM admin_users ORDER BY id DESC"
    admin_list = execute_query(query, fetch_all=True)
    return render_template('admin_list.html', admin_list=admin_list, active_page='admin_acc', sub_page='admin_list')

@admin_bp.route('/add-admin', methods=['GET', 'POST'])
@admin_login_required
def add_new_admin():
    if session.get('admin_role') not in ['Super Admin']:
        flash("You do not have permission to add new administrators.", "danger")
        return redirect(url_for('admin.admin_manage_accounts'))

    if request.method == 'POST':
        fullname = request.form.get('fullname')
        role_access = request.form.get('role_access')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash("Password and Confirm Password do not match.", "danger")
            return redirect(url_for('admin.add_new_admin'))
        
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
             flash("Invalid email format.", "danger")
             return redirect(url_for('admin.add_new_admin'))
        
        hashed_password = generate_password_hash(password)
        query = "INSERT IGNORE INTO admin_users (fullname, role_access, email, password_hash) VALUES (%s, %s, %s, %s)"
        
        if execute_query(query, (fullname, role_access, email, hashed_password)):
            flash(f"New Admin Account for {fullname} ({role_access}) created successfully!", "success")
            return redirect(url_for('admin.admin_manage_accounts'))
        else:
            flash("That email/username already exists or a database error occurred.", "danger")
            
    roles = ['Super Admin', 'Record Staff']
    return render_template('add_new_admin.html', roles=roles, active_page='admin_acc', sub_page='add_new_admin')

@admin_bp.route('/delete-admin/<int:admin_id>', methods=['POST'])
@admin_login_required
def delete_admin(admin_id):
    # Restriction: Super Admin lang ang pwede mag-delete
    if session.get('admin_role') != 'Super Admin':
        flash("Unauthorized: Only Super Admin can delete accounts.", "danger")
        return redirect(url_for('admin.admin_manage_accounts'))
        
    current_admin = execute_query("SELECT email FROM admin_users WHERE id = %s", (admin_id,), fetch_one=True)
    
    if current_admin:
        # Restriction: Bawal i-delete ang sarili
        if current_admin['email'] == session.get('admin_email'):
            flash("You cannot delete your own account.", "danger")
        else:
            execute_query("DELETE FROM admin_users WHERE id = %s", (admin_id,))
            flash("Admin account deleted successfully.", "success")
    else:
        flash("Account not found.", "danger")
        
    return redirect(url_for('admin.admin_manage_accounts'))

@admin_bp.route('/toggle-status/<int:admin_id>', methods=['POST'])
@admin_login_required
def toggle_admin_status(admin_id):
    if session.get('admin_role') != 'Super Admin':
        flash("Only Super Admin can change account status.", "danger")
        return redirect(url_for('admin.admin_manage_accounts'))
        
    current_admin = execute_query("SELECT status, fullname, email FROM admin_users WHERE id = %s", (admin_id,), fetch_one=True)
    
    if current_admin and current_admin['email'] != session['admin_email']:
        new_status = 'Inactive' if current_admin['status'] == 'Active' else 'Active'
        execute_query("UPDATE admin_users SET status = %s WHERE id = %s", (new_status, admin_id))
        flash(f"Status for {current_admin['fullname']} updated to **{new_status}**.", "success")
    elif current_admin and current_admin['email'] == session['admin_email']:
        flash("You cannot change your own account status.", "danger")
    else:
        flash("Admin account not found.", "danger")
    
    return redirect(url_for('admin.admin_manage_accounts'))

# ---------------------------------------------------------
# SEPARATE EMAIL FUNCTION PARA SA MESSAGE REPLIES
# ---------------------------------------------------------
def send_admin_reply_email(recipient_email, original_message, admin_reply):
    url = "https://api.brevo.com/v3/smtp/email"
    api_key = current_app.config.get('BREVO_API_KEY')
    sender_email = current_app.config.get('BREVO_SENDER_EMAIL')
    sender_name = current_app.config.get('BREVO_SENDER_NAME')

    if not api_key:
        print("ERROR: BREVO_API_KEY is missing in config.")
        return False
    if not sender_email:
        print("ERROR: BREVO_SENDER_EMAIL is missing in config.")
        return False

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: 'Segoe UI', Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background: white; border-radius: 15px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
            <div style="background-color: #0f111a; color: #2cc5ad; padding: 25px; text-align: center;">
                <h2 style="margin: 0; text-transform: uppercase;">Admin Response</h2>
            </div>
            <div style="padding: 30px; color: #333;">
                <p>Hello,</p>
                <p>An administrator has responded to your message:</p>
                
                <div style="background: #f9f9f9; border-left: 4px solid #2cc5ad; padding: 15px; margin: 20px 0;">
                    <p style="margin: 0; font-size: 14px; font-weight: bold;">Your Message:</p>
                    <p style="margin: 5px 0 0 0; font-style: italic; color: #666;">"{original_message}"</p>
                </div>

                <div style="background: #eafffc; border-left: 4px solid #2cc5ad; padding: 15px; margin: 20px 0;">
                    <p style="margin: 0; font-size: 14px; font-weight: bold; color: #2cc5ad;">Official Reply:</p>
                    <p style="margin: 5px 0 0 0; color: #333; line-height: 1.6;">{admin_reply}</p>
                </div>

                <p style="font-size: 13px; color: #888;">If you have more concerns, feel free to contact us again via the portal.</p>
            </div>
            <div style="background: #0f111a; color: white; padding: 15px; text-align: center; font-size: 11px;">
                &copy; 2026 CLAREFILES SYSTEM
            </div>
        </div>
    </body>
    </html>
    """

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": recipient_email}],
        "subject": "RE: Your Message to CLAREFILES Admin",
        "htmlContent": html_body
    }
    
    headers = {"accept": "application/json", "api-key": api_key, "content-type": "application/json"}
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        return response.status_code in [200, 201]
    except Exception as e:
        print(f"Brevo Message Email Error: {e}")
        return False

# ---------------------------------------------------------
# ROUTES
# ---------------------------------------------------------

@admin_bp.route('/admin/messages')
@admin_login_required
def view_messages():
    query = """
        SELECT m.id, m.message_text, m.submitted_at, m.is_read,
               u.email, si.firstname, si.lastname
        FROM student_messages m
        LEFT JOIN users u ON m.user_id = u.id
        LEFT JOIN student_info si ON u.email = si.requester_email
        ORDER BY m.submitted_at DESC
    """
    all_msgs = execute_query(query, fetch_all=True) or []
    execute_query("UPDATE student_messages SET is_read = 1 WHERE is_read = 0")
    return render_template('admin_messages.html', messages=all_msgs)

@admin_bp.route('/admin/reply-message', methods=['POST'])
@admin_login_required
def reply_message():
    email = request.form.get('recipient_email')
    reply_text = request.form.get('admin_reply')
    # Kunin yung message text para sa email template
    msg_data = execute_query("SELECT message_text FROM student_messages WHERE id = (SELECT id FROM student_messages WHERE user_id = (SELECT id FROM users WHERE email = %s) ORDER BY submitted_at DESC LIMIT 1)", (email,), fetch_one=True)
    
    orig_msg = msg_data['message_text'] if msg_data else "Your inquiry"
    
    if send_admin_reply_email(email, orig_msg, reply_text):
        flash(f"Reply successfully sent to {email}!", "success")
    else:
        flash("Reply failed to send. Check API settings.", "danger")
        
    return redirect(url_for('admin.view_messages'))

@admin_bp.route('/admin/delete-message/<int:message_id>', methods=['POST'])
@admin_login_required
def delete_message(message_id):
    execute_query("DELETE FROM student_messages WHERE id = %s", (message_id,))
    flash("Message deleted successfully!", "success")
    return redirect(url_for('admin.view_messages'))