import asyncio
from fastapi import WebSocket, WebSocketDisconnect, Query
import google.genai as genai

from config import logger
from gemini_utils import SYSTEM_PROMPT, send_to_gemini
from speech_utils import transcription_manager
from auth import verify_token
from gcs_utils import upload_conversation

async def audio_receiver(ws: WebSocket, queue: asyncio.Queue):
    """Receives audio chunks from the client and puts them into a queue."""
    try:
        while True:
            data = await ws.receive_bytes()
            await queue.put(data)
    except WebSocketDisconnect:
        logger.info("Client disconnected. Signaling transcription manager to stop.")
        await queue.put(None)
    except Exception as e:
        logger.error(f"Error in audio_receiver: {e}")
        await queue.put(None)

async def websocket_transcribe_endpoint(websocket: WebSocket, token: str = Query(None)):
    """Handles the main WebSocket connection for audio transcription."""
    user = None
    full_transcript = []
    
    try:
        if not token:
            # Cannot close here as the connection is not accepted yet.
            # The client will receive a 403 Forbidden from the server.
            logger.warning("Auth token missing.")
            return
        try:
            user = await verify_token(token)
            await websocket.accept()
            logger.info("WebSocket connection accepted.")
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            # Cannot close here as the connection is not accepted yet.
            return

        client = genai.Client()
        chat_history = [
            {'role': 'user', 'parts': [{'text': SYSTEM_PROMPT}]},
            {'role': 'model', 'parts': [{'text': "Understood. I am ready to assist."}]}
        ]
        audio_queue = asyncio.Queue()
        
        receiver_task = asyncio.create_task(audio_receiver(websocket, audio_queue))
        manager_task = asyncio.create_task(transcription_manager(websocket, audio_queue, client, chat_history, full_transcript))

        await asyncio.gather(receiver_task, manager_task)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected by client during transcription.")
    except Exception as e:
        logger.error(f"An unexpected error occurred in the websocket endpoint: {e}")
    finally:
        logger.info("Session ended. Uploading conversation to GCS.")
        if full_transcript and user:
            conversation_data = {
                "user": user.get("email"),
                "transcript": full_transcript
            }
            upload_conversation(conversation_data)
        # The ASGI server handles the final closing of the connection.

async def websocket_test_text_endpoint(websocket: WebSocket, token: str = Query(None)):
    if not token:
        logger.warning("Auth token missing for test endpoint.")
        return
    try:
        await verify_token(token)
        await websocket.accept()
        logger.info("Test WebSocket connection established.")
    except Exception as e:
        logger.error(f"Authentication failed for test endpoint: {e}")
        return

    try:
        client = genai.Client()
        chat_history = [
            {'role': 'user', 'parts': [{'text': SYSTEM_PROMPT}]},
            {'role': 'model', 'parts': [{'text': "Understood. I am ready to assist."}]}
        ]
        logger.info("Gemini client created and history initialized for test endpoint.")

        while True:
            transcript = await websocket.receive_text()
            logger.info(f"Received transcript for testing: {transcript}")
            await send_to_gemini(websocket, client, chat_history, transcript)

    except WebSocketDisconnect:
        logger.info("Test WebSocket connection closing.")
    except Exception as e:
        logger.error(f"Error in test websocket handler: {e}")