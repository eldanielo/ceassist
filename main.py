import os
from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from auth import verify_token
from websocket_handlers import websocket_transcribe_endpoint, websocket_test_text_endpoint

app = FastAPI()

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in ["/login.html", "/docs", "/openapi.json", "/firebase-config"] or request.url.path.startswith("/ws"):
            return await call_next(request)

        token = request.cookies.get("token")
        if not token:
            return RedirectResponse(url='/login.html')
        
        try:
            await verify_token(token)
            response = await call_next(request)
            return response
        except Exception as e:
            return RedirectResponse(url='/login.html')

app.add_middleware(AuthMiddleware)

@app.get("/firebase-config")
async def get_firebase_config():
    return JSONResponse({
        "apiKey": os.environ.get("FIREBASE_API_KEY"),
        "authDomain": "mineral-concord-394714.firebaseapp.com",
        "projectId": "mineral-concord-394714",
        "storageBucket": "mineral-concord-394714.appspot.com",
        "messagingSenderId": "1029284952383",
        "appId": "1:1029284952383:web:1a2b3c4d5e6f7g8h9i0j"
    })

app.add_api_websocket_route("/ws/transcribe", websocket_transcribe_endpoint)
app.add_api_websocket_route("/ws/test_text", websocket_test_text_endpoint)

app.mount("/", StaticFiles(directory=".", html=True), name="static")

@app.get("/login.html", response_class=HTMLResponse)
async def login_page():
    with open("login.html") as f:
        return HTMLResponse(content=f.read())

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    token = request.cookies.get("token")
    if not token:
        return RedirectResponse(url='/login.html')
    try:
        await verify_token(token)
        with open("index.html") as f:
            return HTMLResponse(content=f.read())
    except Exception as e:
        return RedirectResponse(url='/login.html')