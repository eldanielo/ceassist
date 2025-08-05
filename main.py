import asyncio
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from google.cloud import speech
import google.generativeai as genai
import numpy as np
import librosa
import logging
import os
import uuid
import json
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
STREAM_LIMIT_SECONDS = 290

app = FastAPI()

# --- Gemini System Prompt ---
SYSTEM_PROMPT = """
You are a highly advanced AI assistant for a Google Cloud Customer Engineer (CE).
You are listening in on a live sales call. Your purpose is to provide real-time support.
You have three tasks. For each user transcript you receive, you must choose only ONE of the following actions:

1.  **Answer a direct question:** If the customer asks a direct question, provide a concise, factual answer. Do not use any prefix.
2.  **Provide a proactive tip:** If there is an opportunity for the CE to ask a question or position a product, provide a tip. You **MUST** start this response with the prefix `💡 CE Tip:`.
3.  **Extract a key fact:** If a key fact is mentioned (a number, technology, person, or goal), extract it. You **MUST** start this response with the prefix `FACT:`.

If you have no valuable information to provide for a given piece of transcript, you **MUST** respond with only the single word `EMPTY`.
"""

def get_speech_config():
    diarization_config = speech.SpeakerDiarizationConfig(
        enable_speaker_diarization=True, min_speaker_count=2, max_speaker_count=2
    )
    return speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=SPEECH_API_SAMPLE_RATE,
        language_code="en-US",
        diarization_config=diarization_config,
    )

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

async def transcription_manager(ws: WebSocket, queue: asyncio.Queue, gemini_chat):
    client = speech.SpeechAsyncClient()

    async def send_to_gemini(transcript: str):
        logger.info(f"Sending to Gemini: {transcript}")
        message_id = str(uuid.uuid4())
        response_type = None
        response_stream = None
        
        try:
            response_stream = await gemini_chat.send_message_async(transcript, stream=True)
            is_first_chunk = True
            async for chunk in response_stream:
                if not chunk.text: continue

                payload = chunk.text
                if is_first_chunk:
                    is_first_chunk = False
                    if "EMPTY" in payload:
                        logger.info("Gemini returned EMPTY, skipping.")
                        return

                    if payload.strip().startswith("FACT:"):
                        response_type = "FACT"
                        payload = payload.replace("FACT:", "", 1).lstrip()
                    elif payload.strip().startswith("💡 CE Tip:"):
                        response_type = "TIP"
                    else:
                        response_type = "ANSWER"
                
                message = {
                    "message_id": message_id,
                    "response_type": response_type,
                    "payload": payload,
                }
                await ws.send_text(json.dumps(message))

        except Exception as e:
            logger.error(f"Error sending to Gemini: {e}")
        finally:
            if response_stream:
                await response_stream.resolve()


    while True:
        logger.info("Starting new transcription stream.")
        
        async def google_request_generator():
            yield speech.StreamingRecognizeRequest(
                streaming_config=speech.StreamingRecognitionConfig(
                    config=get_speech_config(), interim_results=True
                )
            )
            while True:
                data = await queue.get()
                if data is None: break
                
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
                    logger.info("Stream limit reached. Restarting.")
                    break

                if not response.results or not response.results[0].alternatives: continue
 
                result = response.results[0]
                transcript_text = result.alternatives[0].transcript
                
                if result.is_final:
                    words_info = result.alternatives[0].words
                    current_speaker_tag = words_info[0].speaker_tag if words_info else 0
                    full_transcript = f"**Speaker {current_speaker_tag}:** "
                    for word_info in words_info:
                        if word_info.speaker_tag != current_speaker_tag:
                            full_transcript += f"\n**Speaker {word_info.speaker_tag}:** "
                            current_speaker_tag = word_info.speaker_tag
                        full_transcript += word_info.word + " "
                    
                    full_transcript = full_transcript.strip()
                    logger.info(f"Final transcript: {full_transcript}")
                    await ws.send_text(json.dumps({"response_type": "TRANSCRIPT", "payload": full_transcript}))
                    await send_to_gemini(full_transcript)
                else:
                    await ws.send_text(json.dumps({"response_type": "INTERIM", "payload": transcript_text}))
        except asyncio.CancelledError:
            logger.info("Transcription manager cancelled.")
            break
        except Exception as e:
            logger.error(f"Error during transcription processing: {e}")
            break

    logger.info("Transcription manager finished.")

@app.websocket("/ws/transcribe")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection established.")

    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        chat = model.start_chat(history=[
            {'role': 'user', 'parts': [SYSTEM_PROMPT]},
            {'role': 'model', 'parts': ["Understood. I am ready to assist."]}
        ])
        logger.info("Gemini chat session started.")

        audio_queue = asyncio.Queue()
        
        receiver_task = asyncio.create_task(audio_receiver(websocket, audio_queue))
        manager_task = asyncio.create_task(transcription_manager(websocket, audio_queue, chat))

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