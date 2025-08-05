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
You are listening in on a live sales call between the CE and a Customer.
Be concise, bullet points only. If there is no information to provide, do not respond.
You purpose is to provide real-time support to the CE in three distinct ways:

1.  **Answering Customer Questions:** When the customer asks a direct question about Google Cloud services, features, pricing, or technical capabilities, provide a concise and accurate answer.
    - Frame these answers neutrally, as if the CE is speaking.
    - Do not start these answers with any special prefix.

2.  **Proactive CE Guidance:** Throughout the conversation, provide proactive advice to the Customer Engineer to help them guide the conversation effectively.
    - This guidance should include suggestions on what Google Cloud products to position, what discovery questions to ask, and what technical advantages to highlight.
    - **Crucially, you must start every piece of proactive guidance with the '💡 CE Tip:' prefix.**

3.  **Extracting Key Facts:** When a key fact is mentioned (e.g., a specific number, a technology name, a key person, a stated business goal or pain point), extract it.
    - **You must start every extracted fact with the 'FACT:' prefix.**

**Your Goal:** Empower the Customer Engineer to win the deal by being their all-knowing, proactive assistant.
"""

def get_speech_config():
    """Returns the Google Speech-to-Text configuration with speaker diarization."""
    diarization_config = speech.SpeakerDiarizationConfig(
        enable_speaker_diarization=True,
        min_speaker_count=2,
        max_speaker_count=2,
    )
    return speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=SPEECH_API_SAMPLE_RATE,
        language_code="en-US",
        diarization_config=diarization_config,
    )

async def audio_receiver(ws: WebSocket, queue: asyncio.Queue):
    """Receives audio from WebSocket and puts it into a queue."""
    try:
        while True:
            data = await ws.receive_bytes()
            await queue.put(data)
    except WebSocketDisconnect:
        logger.info("Client disconnected. Audio receiver is stopping.")
        await queue.put(None)
    except Exception as e:
        logger.error(f"Error in audio_receiver: {e}")
        await queue.put(None)

async def transcription_manager(ws: WebSocket, queue: asyncio.Queue, gemini_chat):
    """Manages the transcription stream, restarting it as needed."""
    client = speech.SpeechAsyncClient()

    async def send_to_gemini(transcript: str):
        logger.info(f"Sending to Gemini: {transcript}")
        message_id = str(uuid.uuid4())
        try:
            response = await gemini_chat.send_message_async(transcript, stream=True)
            async for chunk in response:
                if chunk.text:
                    logger.info(f"Received from Gemini: {chunk.text}")
                    await ws.send_text(f"COACH:{message_id}:{chunk.text}")
        except Exception as e:
            logger.error(f"Error sending to Gemini: {e}")

    while True:
        logger.info("Starting new transcription stream.")
        
        async def google_request_generator():
            yield speech.StreamingRecognizeRequest(
                streaming_config=speech.StreamingRecognitionConfig(
                    config=get_speech_config(),
                    interim_results=True,
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
                    logger.info(f"Stream limit of {STREAM_LIMIT_SECONDS}s reached. Restarting.")
                    break

                if not response.results: continue

                result = response.results[0]
                if not result.alternatives: continue

                transcript_text = result.alternatives[0].transcript
                
                if result.is_final:
                    # Process final transcript with speaker labels
                    words_info = result.alternatives[0].words
                    current_speaker_tag = 0
                    full_transcript = ""
                    for word_info in words_info:
                        if word_info.speaker_tag != current_speaker_tag:
                            full_transcript += f"\n**Speaker {word_info.speaker_tag}:** "
                            current_speaker_tag = word_info.speaker_tag
                        full_transcript += word_info.word + " "
                    
                    logger.info(f"Final transcript: {full_transcript.strip()}")
                    await ws.send_text(f"TRANSCRIPT:{full_transcript.strip()}")
                    await send_to_gemini(full_transcript.strip())
                else:
                    await ws.send_text(f"INTERIM: {transcript_text}")
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
        model = genai.GenerativeModel('gemini-1.5-flash')
        chat = model.start_chat(history=[
            {'role': 'user', 'parts': [SYSTEM_PROMPT]},
            {'role': 'model', 'parts': ["Understood. I am ready to assist. I will analyze the transcript and provide talking points for the Seller."]}
        ])
        logger.info("Gemini chat session started.")

        audio_queue = asyncio.Queue()
        
        receiver_task = asyncio.create_task(audio_receiver(websocket, audio_queue))
        manager_task = asyncio.create_task(transcription_manager(websocket, audio_queue, chat))

        done, pending = await asyncio.wait(
            [receiver_task, manager_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending: task.cancel()
        for task in done: task.result()

    except Exception as e:
        logger.error(f"Error in main websocket handler: {e}")
    finally:
        logger.info("WebSocket connection closing.")
        if not websocket.client_state == websockets.protocol.State.CLOSED:
            await websocket.close()