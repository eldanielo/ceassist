from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from websocket_handlers import websocket_transcribe_endpoint, websocket_test_text_endpoint

app = FastAPI()

app.add_api_websocket_route("/ws/transcribe", websocket_transcribe_endpoint)
app.add_api_websocket_route("/ws/test_text", websocket_test_text_endpoint)

app.mount("/", StaticFiles(directory=".", html=True), name="static")
