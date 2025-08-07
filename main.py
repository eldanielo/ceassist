from fastapi import FastAPI
from config import GEMINI_API_KEY
from websocket_handlers import websocket_transcribe_endpoint, websocket_test_text_endpoint

app = FastAPI()

app.add_api_websocket_route("/ws/transcribe", websocket_transcribe_endpoint)
app.add_api_websocket_route("/ws/test_text", websocket_test_text_endpoint)
