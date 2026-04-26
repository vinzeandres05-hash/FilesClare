import os
from urllib.parse import unquote, urlparse



class Config(object):
    # =========================================================
    # FLASK CORE CONFIGURATION
    # =========================================================
    # IMPORTANT: Use a secure, long, and complex key in production!
    SECRET_KEY = os.environ.get('SECRET_KEY', 'YOUR_SUPER_SECURE_SECRET_KEY_HERE_2025')
    
    # =========================================================
    # MYSQL CONFIGURATION
    # =========================================================
    DATABASE_URL = os.environ.get('DATABASE_URL')

    if DATABASE_URL:
        parsed = urlparse(DATABASE_URL)
        MYSQL_CONFIG = {
            'host': parsed.hostname or 'localhost',
            'port': parsed.port or 3306,
            'user': unquote(parsed.username) if parsed.username else None,
            'password': unquote(parsed.password) if parsed.password else None,
            'database': parsed.path.lstrip('/') if parsed.path else None,
            'charset': 'utf8mb4',
        }
    else:
        MYSQL_CONFIG = {
            'database': 'thesis_db',
            'user': 'root',
            'password': '',
            'host': 'localhost',
            'port': 3306,
            'charset': 'utf8mb4',
        }

    # =========================================================
    # BREVO API CONFIGURATION (NEW)
    # =========================================================
    # Imbes na SMTP settings, API Key na lang ang kailangan natin.
    # Mas safe kung ilalagay mo rin ito sa Environment Variables sa Render.
    BREVO_API_KEY = os.environ.get('BREVO_API_KEY')  
    BREVO_SENDER_EMAIL = os.environ.get('BREVO_SENDER_EMAIL', 'vinzeangeloandres1.scc@gmail.com')
    BREVO_SENDER_NAME = os.environ.get('BREVO_SENDER_NAME', 'ClareFiles System')