import logging
import os
from dotenv import load_dotenv

# --- Environment and API Key Configuration ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env file")

# --- Logging and Constants ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
CHROME_SAMPLE_RATE = 48000
SPEECH_API_SAMPLE_RATE = 16000
STREAM_LIMIT_SECONDS = 290
