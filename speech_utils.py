import asyncio
import json
from google.cloud import speech

from config import logger, SPEECH_API_SAMPLE_RATE, STREAM_LIMIT_SECONDS
from gemini_utils import send_to_gemini

def get_speech_config():
    return speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=SPEECH_API_SAMPLE_RATE,
        language_code="en-US",
    )

async def transcription_manager(ws, queue, genai_client, chat_history, full_transcript):
    speech_client = speech.SpeechAsyncClient()

    async def google_request_generator():
        yield speech.StreamingRecognizeRequest(
            streaming_config=speech.StreamingRecognitionConfig(
                config=get_speech_config(), interim_results=True
            )
        )
        while True:
            data = await queue.get()
            if data is None:
                break
            yield speech.StreamingRecognizeRequest(audio_content=data)
            queue.task_done()

    stream_start_time = asyncio.get_event_loop().time()
    try:
        responses = await speech_client.streaming_recognize(requests=google_request_generator())
        async for response in responses:
            if asyncio.get_event_loop().time() - stream_start_time > STREAM_LIMIT_SECONDS:
                logger.info("Stream limit reached. Sending restart message.")
                await ws.send_text(json.dumps({"response_type": "RESTART"}))
                break

            if not response.results or not response.results[0].alternatives:
                continue

            result = response.results[0]
            transcript_text = result.alternatives[0].transcript

            if result.is_final:
                transcript = result.alternatives[0].transcript.strip()
                if transcript:
                    full_transcript.append(transcript)
                    await ws.send_text(json.dumps({"response_type": "TRANSCRIPT", "payload": transcript}))
                    await send_to_gemini(ws, genai_client, chat_history, transcript)
            else:
                if transcript_text:
                    await ws.send_text(json.dumps({"response_type": "INTERIM", "payload": transcript_text}))
    except asyncio.CancelledError:
        logger.info("Transcription manager cancelled.")
    except Exception as e:
        logger.error(f"Error during transcription processing: {e}")
    finally:
        logger.info("Transcription manager finished.")