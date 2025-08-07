import asyncio
import json
import librosa
import numpy as np
from google.cloud import speech

from config import logger, CHROME_SAMPLE_RATE, SPEECH_API_SAMPLE_RATE, STREAM_LIMIT_SECONDS
from gemini_utils import send_to_gemini

def get_speech_config():
    return speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=SPEECH_API_SAMPLE_RATE,
        language_code="en-US",
    )

async def transcription_manager(ws, queue, genai_client, chat_history):
    speech_client = speech.SpeechAsyncClient()

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
            responses = await speech_client.streaming_recognize(requests=google_request_generator())
            async for response in responses:
                if asyncio.get_event_loop().time() - stream_start_time > STREAM_LIMIT_SECONDS:
                    logger.info("Stream limit reached. Restarting.")
                    break

                if not response.results or not response.results[0].alternatives: continue
 
                result = response.results[0]
                transcript_text = result.alternatives[0].transcript
                
                if result.is_final:
                    full_transcript = result.alternatives[0].transcript.strip()
                    logger.info(f"Final transcript: {full_transcript}")
                    await ws.send_text(json.dumps({"response_type": "TRANSCRIPT", "payload": full_transcript}))
                    await send_to_gemini(ws, genai_client, chat_history, full_transcript)
                else:
                    await ws.send_text(json.dumps({"response_type": "INTERIM", "payload": transcript_text}))
        except asyncio.CancelledError:
            logger.info("Transcription manager cancelled.")
            break
        except Exception as e:
            logger.error(f"Error during transcription processing: {e}")
            break

    logger.info("Transcription manager finished.")
