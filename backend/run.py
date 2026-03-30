from pathlib import Path
from dotenv import load_dotenv

# Always load backend/.env no matter where the process is started from.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5002)
