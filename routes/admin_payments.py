from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session, jsonify
from db import execute_query
import requests
from .admin import admin_login_required

admin_pay_bp = Blueprint('admin_payment', __name__)

# ---------------------------------------------------------
# SEPARATE EMAIL FUNCTION FOR PAYMENT REJECTION
# ---------------------------------------------------------
def send_payment_rejection_email(request_data, reason):
    url = "https://api.brevo.com/v3/smtp/email"
    api_key = current_app.config.get('BREVO_API_KEY')
    sender_email = current_app.config.get('BREVO_SENDER_EMAIL')
    sender_name = current_app.config.get('BREVO_SENDER_NAME')

    recipient_email = request_data.get('requester_email')
    request_id = request_data.get('id')
    document = request_data.get('document')

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: auto; border: 1px solid #ddd; border-radius: 10px; overflow: hidden;">
            <div style="background-color: #e74c3c; color: white; padding: 20px; text-align: center;">
                <h2>PAYMENT REJECTED</h2>
            </div>
            <div style="padding: 20px;">
                <p>Hello,</p>
                <p>Your payment for request <b>#{request_id} ({document})</b> has been rejected by the administrator.</p>
                <div style="background: #f9f9f9; border-left: 5px solid #e74c3c; padding: 15px; margin: 20px 0;">
                    <b>REASON FOR REJECTION:</b><br>
                    {reason}
                </div>
                <p>Please log in to your portal to re-upload your proof of payment or correct the details.</p>
            </div>
            <div style="background: #0f111a; color: white; padding: 15px; text-align: center; font-size: 12px;">
                &copy; 2026 CLAREFILES SYSTEM
            </div>
        </div>
    </body>
    </html>
    """

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": recipient_email}],
        "subject": f"ALERT: Payment Rejected for Request #{request_id}",
        "htmlContent": html_body
    }
    
    headers = {"accept": "application/json", "api-key": api_key, "content-type": "application/json"}
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        return response.status_code in [200, 201]
    except Exception as e:
        print(f"Email error: {e}")
        return False

# ---------------------------------------------------------
# ROUTES
# ---------------------------------------------------------

@admin_pay_bp.route('/admin/payments/<status>')
@admin_login_required
def manage_payments(status):
    status_map = {
        'pending': 'Pending Verification',
        'verified': 'PAID',
        'rejected': 'REJECTED',
        'paymongo': 'PAID'  # Special for PayMongo only
    }
    db_status = status_map.get(status, 'Pending Verification')

    # Get admin role and ID from session
    admin_role = session.get('admin_role')
    admin_id = session.get('admin_id')

    # Build query with role-based filtering
    base_query = """
        SELECT p.id AS pay_id, r.id AS req_id, r.firstname, r.lastname,
               p.amount_paid, p.reference_no, p.proof_image, p.payment_status
        FROM payments p
        JOIN requests r ON p.request_id = r.id
        WHERE p.payment_status = %s
    """
    
    if status == 'paymongo':
        base_query += " AND p.proof_image = 'paymongo_verified.png'"
    
    base_query += " ORDER BY p.date_uploaded DESC"
    
    if admin_role == 'Super Admin':
        # Super Admin sees all payments
        payments = execute_query(base_query, (db_status,), fetch_all=True)
    else:
        # Record Staff only sees payments for requests they accepted
        base_query = base_query.replace("WHERE p.payment_status = %s", "WHERE p.payment_status = %s AND r.assigned_admin_id = %s")
        payments = execute_query(base_query, (db_status, admin_id), fetch_all=True)

    return render_template('admin_paymentverify.html', payments=payments, current_status=status)

@admin_pay_bp.route('/admin/approve/<int:pay_id>/<int:req_id>')
@admin_login_required
def approve_payment(pay_id, req_id):
    request_data = execute_query('SELECT id, requester_email, document, final_price FROM requests WHERE id = %s', (req_id,), fetch_one=True)

    if request_data:
        execute_query("UPDATE payments SET payment_status = 'PAID' WHERE id = %s", (pay_id,))
        execute_query("UPDATE requests SET status = 'Processing', updated_at = NOW() WHERE id = %s", (req_id,))
        execute_query(
            "INSERT INTO request_history (request_id, admin_id, status) VALUES (%s, %s, %s)",
            (req_id, None, 'Processing')
        )
        
        try:
            # Gamit ang existing function sa admin.py
            from .admin import send_status_update_email 
            send_status_update_email(request_data, 'Processing')
        except Exception as e:
            print(f"Email error: {e}")
        
        flash(f"Payment for Request #{req_id} approved!", "success")
    
    return redirect(url_for('admin_payment.manage_payments', status='pending'))

@admin_pay_bp.route('/admin/reject', methods=['POST'])
@admin_login_required
def reject_payment():
    pay_id = request.form.get('pay_id')
    req_id = request.form.get('req_id')
    reason = request.form.get('reason')

    # Update status sa Database
    execute_query("UPDATE payments SET payment_status = 'REJECTED' WHERE id = %s", (pay_id,))
    
    # Kunin ang info para sa email
    request_data = execute_query('SELECT id, requester_email, document FROM requests WHERE id = %s', (req_id,), fetch_one=True)
    
    if request_data:
        send_payment_rejection_email(request_data, reason)
        flash(f"Payment for Request #{req_id} rejected and email sent.", "warning")
    
    return redirect(url_for('admin_payment.manage_payments', status='pending'))

@admin_pay_bp.route('/admin/delete/<int:pay_id>/<int:req_id>/<status>')
@admin_login_required
def delete_payment(pay_id, req_id, status):
    # Buburahin lang ang record sa payments table.
    # Kapag status = 'verified' kanina, ang r.status ay 'Processing' na kaya PAID pa rin lalabas.
    # Kapag status = 'rejected' kanina, ang r.status ay 'Accepted' pa rin dapat, kaya UNPAID na siya ulit.
    execute_query("DELETE FROM payments WHERE id = %s", (pay_id,))
    
    flash(f"Record deleted successfully.", "info")
    return redirect(url_for('admin_payment.manage_payments', status=status))

@admin_pay_bp.route('/admin/notification/read/<int:notif_id>')
@admin_login_required
def mark_read(notif_id):
    admin_id = session.get('admin_id')
    admin_role = session.get('admin_role')
    
    if admin_id:
        if admin_role == 'Super Admin':
            # Super Admin can mark any notification as read
            notif = execute_query("SELECT category FROM notifications WHERE id = %s", (notif_id,), fetch_one=True)
        else:
            # Regular staff can only mark their own notifications
            notif = execute_query(
                "SELECT category FROM notifications WHERE id = %s AND (admin_id = %s OR admin_id IS NULL)",
                (notif_id, admin_id),
                fetch_one=True
            )
    else:
        notif = execute_query("SELECT category FROM notifications WHERE id = %s", (notif_id,), fetch_one=True)
    
    if notif:
        if admin_id:
            if admin_role == 'Super Admin' or admin_role == 'Record Staff':
                # Super Admin can mark any notification as read
                execute_query("UPDATE notifications SET is_read = 1 WHERE id = %s", (notif_id,))
            else:
                # Regular staff can only mark their own notifications
                execute_query("UPDATE notifications SET is_read = 1 WHERE id = %s AND (admin_id = %s OR admin_id IS NULL)", (notif_id, admin_id))
        else:
            execute_query("UPDATE notifications SET is_read = 1 WHERE id = %s", (notif_id,))
        if notif['category'] == 'payment':
            return redirect(url_for('admin_payment.manage_payments', status='pending'))
    return redirect(url_for('admin.admin', menu_type='pending_requests'))

@admin_pay_bp.route('/admin/notification/read-all')
@admin_login_required
def mark_all_read():
    admin_id = session.get('admin_id')
    admin_role = session.get('admin_role')
    
    if admin_id:
        if admin_role == 'Super Admin':
            # Super Admin can mark all notifications as read
            execute_query("UPDATE notifications SET is_read = 1")
        else:
            # Regular staff can only mark their own notifications
            execute_query("UPDATE notifications SET is_read = 1 WHERE admin_id = %s OR admin_id IS NULL", (admin_id,))
    else:
        execute_query("UPDATE notifications SET is_read = 1")
    flash("All notifications marked as read.", "info")
    return redirect(request.referrer or url_for('admin.admin'))

@admin_pay_bp.route('/admin/notification/clear-all')
@admin_login_required
def clear_all_notifications():
    execute_query("DELETE FROM notifications")
    flash("All notifications cleared.", "success")
    return redirect(request.referrer or url_for('admin.admin'))

@admin_pay_bp.route('/admin/notifications/live')
@admin_login_required
def live_notifications():
    admin_id = session.get('admin_id')
    admin_role = session.get('admin_role')

    if admin_role == 'Super Admin':
        payment_count_row = execute_query(
            "SELECT COUNT(*) as count FROM notifications WHERE is_read = 0 AND category = 'payment'",
            fetch_one=True
        )
        request_count_row = execute_query(
            "SELECT COUNT(*) as count FROM notifications WHERE is_read = 0 AND category = 'request'",
            fetch_one=True
        )
        latest_notifications = execute_query(
            "SELECT id, message, category, is_read, created_at FROM notifications ORDER BY created_at DESC LIMIT 5",
            fetch_all=True
        )
    else:
        payment_count_row = execute_query(
            "SELECT COUNT(*) as count FROM notifications WHERE is_read = 0 AND category = 'payment' AND (admin_id = %s OR admin_id IS NULL)",
            (admin_id,),
            fetch_one=True
        )
        request_count_row = execute_query(
            "SELECT COUNT(*) as count FROM notifications WHERE is_read = 0 AND category = 'request' AND (admin_id = %s OR admin_id IS NULL)",
            (admin_id,),
            fetch_one=True
        )
        latest_notifications = execute_query(
            "SELECT id, message, category, is_read, created_at FROM notifications WHERE admin_id = %s OR admin_id IS NULL ORDER BY created_at DESC LIMIT 5",
            (admin_id,),
            fetch_all=True
        )

    notif_count = payment_count_row['count'] if payment_count_row else 0
    pending_req_count = request_count_row['count'] if request_count_row else 0

    payload_notifications = []
    if latest_notifications:
        for item in latest_notifications:
            created_at = item.get('created_at')
            if created_at and hasattr(created_at, 'strftime'):
                created_at_text = created_at.strftime('%b %d, %I:%M %p')
            else:
                created_at_text = ''

            payload_notifications.append({
                'id': item.get('id'),
                'message': item.get('message') or '',
                'category': item.get('category') or '',
                'is_read': item.get('is_read', 0),
                'created_at_text': created_at_text
            })

    return jsonify({
        'notif_count': notif_count,
        'pending_req_count': pending_req_count,
        'total_badge_count': notif_count + pending_req_count,
        'notifs': payload_notifications
    })