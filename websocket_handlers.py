import asyncio
import websockets
from fastapi import WebSocket, WebSocketDisconnect
import google.genai as genai

from config import logger
from gemini_utils import SYSTEM_PROMPT, send_to_gemini
from speech_utils import transcription_manager

async def audio_receiver(ws: WebSocket, queue: asyncio.Queue):
    try:
        while True:
            await queue.put(await ws.receive_bytes())
    except WebSocketDisconnect:
        logger.info("Client disconnected. Audio receiver stopping.")
        await queue.put(None)
    except Exception as e:
        logger.error(f"Error in audio_receiver: {e}")
        await queue.put(None)

async def websocket_transcribe_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection established.")

    try:
        client = genai.Client()
        chat_history = [
            {'role': 'user', 'parts': [{'text': SYSTEM_PROMPT}]},
            {'role': 'model', 'parts': [{'text': "Understood. I am ready to assist."}]}
        ]
        logger.info("Gemini client created and history initialized.")

        audio_queue = asyncio.Queue()
        
        receiver_task = asyncio.create_task(audio_receiver(websocket, audio_queue))
        manager_task = asyncio.create_task(transcription_manager(websocket, audio_queue, client, chat_history))

        done, pending = await asyncio.wait(
            [receiver_task, manager_task], return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending: task.cancel()
        for task in done: task.result()

    except Exception as e:
        logger.error(f"Error in main websocket handler: {e}")
    finally:
        logger.info("WebSocket connection closing.")
        if not websocket.client_state == websockets.protocol.State.CLOSED:
            await websocket.close()

async def websocket_test_text_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Test WebSocket connection established.")

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