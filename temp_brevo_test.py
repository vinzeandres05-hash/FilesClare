from dotenv import load_dotenv
load_dotenv()
from flask import Flask
from config import Config
from routes.user import send_otp_email
app = Flask(__name__)
app.config.from_object(Config)
with app.app_context():
    print('BREVO_API_KEY', app.config.get('BREVO_API_KEY'))
    print('SEND RESULT', send_otp_email('test@example.com', '123456'))
