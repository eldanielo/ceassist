import asyncio
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from google.cloud import speech
import google.generativeai as genai
from google.generativeai.types import Tool
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

# --- Gemini Tool Definitions ---
ce_assist_tool = Tool(function_declarations=[
    {
        "name": "extract_fact",
        "description": "Extract a key fact from the transcript.",
        "parameters": {
            "type": "object",
            "properties": {
                "fact": {
                    "type": "string",
                    "description": "The key fact, such as a number, technology, person, or goal. Should be keywords only."
                },
                "category": {
                    "type": "string",
                    "description": "The category of the fact. Must be either 'infrastructure' or 'other'."
                },
                "gcp_service": {
                    "type": "string",
                    "description": "The equivalent GCP service for an infrastructure fact. Only provide if the category is 'infrastructure' and a clear equivalent exists."
                }
            },
            "required": ["fact", "category"]
        }
    },
    {
        "name": "provide_tip",
        "description": "Provide a proactive tip for the Customer Engineer.",
        "parameters": {
            "type": "object",
            "properties": {
                "short_tip": {
                    "type": "string",
                    "description": "A short, keyword-based version of the tip."
                },
                "long_tip": {
                    "type": "string",
                    "description": "A longer, more detailed version of the tip."
                }
            },
            "required": ["short_tip", "long_tip"]
        }
    },
    {
        "name": "answer_question",
        "description": "Answer a direct question from the customer.",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "A short, keyword-based summary of the customer's question."
                },
                "short_answer": {
                    "type": "string",
                    "description": "A short, keyword-based answer to the customer's question."
                },
                "long_answer": {
                    "type": "string",
                    "description": "A longer, more detailed answer to the customer's question."
                }
            },
            "required": ["question", "short_answer", "long_answer"]
        }
    }
])


# --- Gemini System Prompt ---
SYSTEM_PROMPT = """
You are a highly advanced AI assistant for a Google Cloud Customer Engineer (CE).
You are listening in on a live sales call. Your purpose is to provide real-time support.
For each user transcript you receive, you must use the provided tools to respond.

Your primary goal is to help the CE. Therefore, you should always look for opportunities to `provide_tip`.

- `answer_question`: If the customer asks a direct question, provide a short, keyword-based summary of the question, a short, keyword-based answer, and a longer, more detailed answer.
- `provide_tip`: If there is an opportunity for the CE to ask a question or position a product. This is your most important function. Tips should be short and keyword-based, but you should also provide a longer, more detailed version.
- `extract_fact`: If a key fact is mentioned (a number, technology, person, or goal), categorize it as either 'infrastructure' or 'other'. If the category is 'infrastructure', provide the equivalent GCP service if one exists. Facts should be concise and to the point. For example, instead of "The entire infrastructure is on AWS", say "100% AWS". Instead of "Their application is built with React", say "React". facts should also usually trigger provide_tip

If you have no valuable information to provide, do not call any tool.
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

async def send_to_gemini(ws: WebSocket, gemini_chat, transcript: str):
    logger.info(f"Sending to Gemini: {transcript}")
    
    try:
        response = await gemini_chat.send_message_async(transcript)
        
        if not response.candidates or not response.candidates[0].content.parts:
            logger.info("Gemini returned no response, skipping.")
            await ws.send_text(json.dumps({"response_type": "EMPTY"}))
            return

        function_called = False
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'function_call') and part.function_call:
                function_called = True
                fc = part.function_call
                
                message_id = str(uuid.uuid4())
                response_type = ""
                payload = {}

                if fc.name == "extract_fact":
                    response_type = "FACT"
                    payload = {"fact": fc.args['fact'], "category": fc.args['category']}
                    if 'gcp_service' in fc.args:
                        payload['gcp_service'] = fc.args['gcp_service']
                elif fc.name == "provide_tip":
                    response_type = "TIP"
                    payload = {"short": f"💡 {fc.args['short_tip']}", "long": fc.args['long_tip']}
                elif fc.name == "answer_question":
                    response_type = "ANSWER"
                    payload = {"question": fc.args['question'], "short": fc.args['short_answer'], "long": fc.args['long_answer']}
                else:
                    logger.warning(f"Unknown function call: {fc.name}")
                    continue

                message = {
                    "message_id": message_id,
                    "response_type": response_type,
                    "payload": payload,
                }
                logger.info(f"Gemini response: {json.dumps(message)}")
                await ws.send_text(json.dumps(message))

        if not function_called:
            logger.info("Gemini did not call a function.")
            await ws.send_text(json.dumps({"response_type": "EMPTY"}))

    except Exception as e:
        logger.error(f"Error sending to Gemini: {e}")


async def transcription_manager(ws: WebSocket, queue: asyncio.Queue, gemini_chat):
    client = speech.SpeechAsyncClient()

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
                    await send_to_gemini(ws, gemini_chat, full_transcript)
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
        model = genai.GenerativeModel('gemini-2.5-flash', tools=[ce_assist_tool])
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

@app.websocket("/ws/test_text")
async def websocket_test_text_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Test WebSocket connection established.")

    try:
        model = genai.GenerativeModel('gemini-2.5-flash', tools=[ce_assist_tool])
        chat = model.start_chat(history=[
            {'role': 'user', 'parts': [SYSTEM_PROMPT]},
            {'role': 'model', 'parts': ["Understood. I am ready to assist."]}
        ])
        logger.info("Gemini chat session started for test endpoint.")

        while True:
            transcript = await websocket.receive_text()
            logger.info(f"Received transcript for testing: {transcript}")
            await send_to_gemini(websocket, chat, transcript)

    except WebSocketDisconnect:
        logger.info("Test WebSocket connection closing.")
    except Exception as e:
        logger.error(f"Error in test websocket handler: {e}")