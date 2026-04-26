from dotenv import load_dotenv
load_dotenv()
from app import app

with app.test_client() as client:
    resp = client.post('/login', data={'email': 'test@example.com'}, follow_redirects=True)
    print('STATUS', resp.status_code)
    print(resp.data.decode()[:1000])
