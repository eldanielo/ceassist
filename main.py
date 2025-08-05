import asyncio
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from google.cloud import speech
import google.generativeai as genai
import numpy as np
import librosa
import logging
import os
from dotenv import load_dotenv

# --- Environment and API Key Configuration ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env file")
genai.configure(api_key=GEMINI_API_KEY)

# --- Logging and Constants ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
CHROME_SAMPLE_RATE = 48000
SPEECH_API_SAMPLE_RATE = 16000
STREAM_LIMIT_SECONDS = 290  # Restart stream every ~4.8 minutes

app = FastAPI()

# --- Gemini System Prompt ---
SYSTEM_PROMPT = """
You are an expert sales assistant and coach. Your name is 'Coach'. 
You are listening to a sales call between a 'Seller' (our user) and a 'Customer'.
The transcript of their conversation will be provided in real-time.

Your mission is to help the Seller win the sale.

Rules:
- DO NOT summarize the conversation.
- DO provide short, actionable talking points for the Seller only.
- Keep your talking points to 1-2 sentences.
- Identify customer pain points, buying signals, and objections.
- Suggest specific questions the Seller should ask.
- Recommend which product features to highlight based on the customer's needs.
- Frame your advice as if you are speaking directly to the Seller.
- Start each talking point with a '💡' emoji.
"""

async def audio_receiver(ws: WebSocket, queue: asyncio.Queue):
    """Receives audio from WebSocket and puts it into a queue."""
    try:
        while True:
            data = await ws.receive_bytes()
            await queue.put(data)
    except WebSocketDisconnect:
        logger.info("Client disconnected. Audio receiver is stopping.")
        await queue.put(None)  # Signal the end of audio
    except Exception as e:
        logger.error(f"Error in audio_receiver: {e}")
        await queue.put(None)

async def transcription_manager(ws: WebSocket, queue: asyncio.Queue, gemini_chat):
    """Manages the transcription stream, restarting it as needed."""
    is_customer_turn = True
    client = speech.SpeechAsyncClient()

    async def send_to_gemini(transcript: str, is_customer: bool):
        speaker = "Customer" if is_customer else "Seller"
        formatted_transcript = f"{speaker}: {transcript}"
        logger.info(f"Sending to Gemini: {formatted_transcript}")
        try:
            response = await gemini_chat.send_message_async(formatted_transcript, stream=True)
            async for chunk in response:
                if chunk.text:
                    logger.info(f"Received from Gemini: {chunk.text}")
                    await ws.send_text(f"COACH: {chunk.text}")
        except Exception as e:
            logger.error(f"Error sending to Gemini: {e}")

    while True:  # Loop to restart the stream
        logger.info("Starting new transcription stream.")
        
        async def google_request_generator():
            streaming_config = speech.StreamingRecognitionConfig(
                config=speech.RecognitionConfig(
                    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                    sample_rate_hertz=SPEECH_API_SAMPLE_RATE,
                    language_code="en-US",
                ),
                interim_results=True,
            )
            yield speech.StreamingRecognizeRequest(streaming_config=streaming_config)

            while True:
                data = await queue.get()
                if data is None:
                    break
                
                audio_np = np.frombuffer(data, dtype=np.int16)
                audio_float = audio_np.astype(np.float32) / 32768.0
                resampled_audio_float = await asyncio.to_thread(
                    librosa.resample, y=audio_float, orig_sr=CHROME_SAMPLE_RATE, target_sr=SPEECH_API_SAMPLE_RATE
                )
                resampled_audio_np = (resampled_audio_float * 32767).astype(np.int16)
                yield speech.StreamingRecognizeRequest(audio_content=resampled_audio_np.tobytes())
                queue.task_done()

        stream_start_time = asyncio.get_event_loop().time()
        try:
            responses = await client.streaming_recognize(requests=google_request_generator())
            async for response in responses:
                if asyncio.get_event_loop().time() - stream_start_time > STREAM_LIMIT_SECONDS:
                    logger.info(f"Stream limit of {STREAM_LIMIT_SECONDS}s reached. Restarting.")
                    break

                if not response.results:
                    continue

                transcript = response.results[0].alternatives[0].transcript
                if response.results[0].is_final:
                    logger.info(f"Final transcript: {transcript}")
                    await ws.send_text(f"TRANSCRIPT: {transcript}")
                    await send_to_gemini(transcript, is_customer_turn)
                    is_customer_turn = not is_customer_turn
                else:
                    await ws.send_text(f"INTERIM: {transcript}")
        except asyncio.CancelledError:
            logger.info("Transcription manager cancelled.")
            break
        except Exception as e:
            logger.error(f"Error during transcription processing: {e}")
            break # Exit the while loop on other errors

    logger.info("Transcription manager finished.")


@app.websocket("/ws/transcribe")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection established.")

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        chat = model.start_chat(history=[
            {'role': 'user', 'parts': [SYSTEM_PROMPT]},
            {'role': 'model', 'parts': ["Understood. I am ready to assist the Seller. I will provide talking points starting with '💡'."]}
        ])
        logger.info("Gemini chat session started.")

        audio_queue = asyncio.Queue()
        
        receiver_task = asyncio.create_task(audio_receiver(websocket, audio_queue))
        manager_task = asyncio.create_task(transcription_manager(websocket, audio_queue, chat))

        done, pending = await asyncio.wait(
            [receiver_task, manager_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
        for task in done:
            task.result() # Raise exceptions if any

    except Exception as e:
        logger.error(f"Error in main websocket handler: {e}")
    finally:
        logger.info("WebSocket connection closing.")
        if not websocket.client_state == websockets.protocol.State.CLOSED:
            await websocket.close()