# run.py
import os
from dotenv import load_dotenv

load_dotenv()

from app import create_app

app = create_app()

if __name__ == '__main__':
    env = os.getenv('FLASK_ENV', 'development')
    print(f"Starting Flask app in {env} mode on http://0.0.0.0:8080 (for local testing)")
    app.run(
        debug=env == 'development',
        port=8080,
        host='0.0.0.0'
    )