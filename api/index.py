import sys
from pathlib import Path

# Ensure project root directory is in sys.path for Vercel serverless environment
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import app

# Expose app for Vercel serverless function execution
