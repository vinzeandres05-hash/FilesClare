import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from db import execute_query

upload_bp = Blueprint('upload', __name__)
UPLOAD_FOLDER = os.path.join('static', 'uploads', 'proofs')

@upload_bp.route('/upload-proof', methods=['GET', 'POST'])
def upload_proof():
    if 'user_email' not in session:
        flash("Please log in to upload payment proof.", "danger")
        return redirect(url_for('user.login'))

    user_email = session['user_email']

    if request.method == 'POST':
        req_id = request.form.get('req_id')
        amount = request.form.get('amount')
        ref_no = request.form.get('ref_no')
        file = request.files.get('proof_file')

        # 1. Validation: Siguraduhing hindi empty ang input
        if not req_id or not amount or not ref_no or not file:
            flash("All fields are required!", "danger")
            return redirect(request.url)

        # 2. Safety Check: Exist ba talaga ang Request ID sa database?
        check_query = "SELECT id, requester_email FROM requests WHERE id = %s"
        existing_req = execute_query(check_query, (req_id,), fetch_one=True)

        if not existing_req:
            flash(f"Error: Request ID #{req_id} does not exist. Please check your ID.", "danger")
            return redirect(request.url)

        if existing_req.get('requester_email') != user_email:
            flash("You can only upload proof for your own request.", "danger")
            return redirect(request.url)

        # 3. File Saving Logic
        if file and file.filename != '':
            if not os.path.exists(UPLOAD_FOLDER):
                os.makedirs(UPLOAD_FOLDER)

            filename = secure_filename(f"PAY_REQ{req_id}_{ref_no}.png")
            file.save(os.path.join(UPLOAD_FOLDER, filename))

            # 4. Database Insert/Update
            query = """
                INSERT INTO payments (request_id, reference_no, amount_paid, proof_image)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    reference_no = VALUES(reference_no),
                    amount_paid = VALUES(amount_paid),
                    proof_image = VALUES(proof_image),
                    payment_status = 'Pending Verification';
            """
            execute_query(query, (req_id, ref_no, amount, filename))
            
            # Get the admin who accepted this request
            admin_query = "SELECT assigned_admin_id FROM requests WHERE id = %s"
            admin_result = execute_query(admin_query, (req_id,), fetch_one=True)
            
            notif_msg = f"New payment proof uploaded for Request #{req_id}"
            
            # Notify the assigned admin if exists
            if admin_result and admin_result['assigned_admin_id']:
                execute_query("INSERT INTO notifications (message, category, admin_id) VALUES (%s, 'payment', %s)", (notif_msg, admin_result['assigned_admin_id']))
            
            # Always notify all Super Admins
            super_admin_query = "SELECT id FROM admin_users WHERE role_access = 'Super Admin'"
            super_admins = execute_query(super_admin_query, fetch_all=True)
            for super_admin in super_admins:
                execute_query("INSERT INTO notifications (message, category, admin_id) VALUES (%s, 'payment', %s)", (notif_msg, super_admin['id']))
            
            flash(f"Proof for Request #{req_id} submitted! Wait for approval.", "success")
            return redirect(url_for('upload.upload_proof')) # O kung saan mo gusto i-redirect

    return render_template('upload_proof.html')