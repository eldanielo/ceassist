import asyncio
import websockets
from fastapi import FastAPI, WebSocket
from google.cloud import speech
import numpy as np
import librosa
import logging

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# --- Audio Resampling Configuration ---
CHROME_SAMPLE_RATE = 48000
SPEECH_API_SAMPLE_RATE = 16000

@app.websocket("/ws/transcribe")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection established.")

    client = speech.SpeechAsyncClient()
    recognition_config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=SPEECH_API_SAMPLE_RATE,
        language_code="en-US",
    )
    streaming_config = speech.StreamingRecognitionConfig(
        config=recognition_config,
        interim_results=True,
    )

    async def request_generator():
        yield speech.StreamingRecognizeRequest(streaming_config=streaming_config)
        while True:
            try:
                data = await websocket.receive_bytes()
                if not data:
                    break
                
                audio_np = np.frombuffer(data, dtype=np.int16)
                
                # Convert to float for resampling
                audio_float = audio_np.astype(np.float32) / 32768.0
                
                resampled_audio_float = await asyncio.to_thread(
                    librosa.resample, y=audio_float, orig_sr=CHROME_SAMPLE_RATE, target_sr=SPEECH_API_SAMPLE_RATE
                )

                # Convert back to 16-bit PCM
                resampled_audio_np = (resampled_audio_float * 32767).astype(np.int16)

                yield speech.StreamingRecognizeRequest(audio_content=resampled_audio_np.tobytes())

            except websockets.exceptions.ConnectionClosedOK:
                logger.info("Client connection closed gracefully.")
                break
            except Exception as e:
                logger.error(f"Error receiving audio: {e}")
                break

    try:
        responses = await client.streaming_recognize(requests=request_generator())

        async for response in responses:
            for result in response.results:
                transcript = result.alternatives[0].transcript
                if result.is_final:
                    logger.info(f"Final transcript: {transcript}")
                    text_accumulator.append(transcript + " ")
                    await websocket.send_text(f"TRANSCRIPT: {transcript}")
                else:
                    logger.info(f"Interim transcript: {transcript}")
                    await websocket.send_text(f"INTERIM: {transcript}")


    except Exception as e:
        logger.error(f"Error during transcription: {e}")
    finally:
        logger.info("WebSocket connection closed.")
        await websocket.close()