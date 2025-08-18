import asyncio
import websockets
import json
import time

# List of mock transcripts to simulate a conversation
MOCK_TRANSCRIPTS = [
    "Hello, thanks for joining the call today. We're excited to show you what we've been working on.",
    "We're currently running our entire infrastructure on AWS, and it's becoming very expensive.",
    "Our main goal is to reduce our cloud spending by at least 30% over the next year.",
    "We're also concerned about vendor lock-in and want to explore multi-cloud strategies.",
    "What can you tell me about Google's approach to multi-cloud?",
    "That's interesting. How does Google's Anthos platform compare to AWS Outposts?",
    "We're also looking to improve our data analytics capabilities. We're using a mix of Redshift and some open-source tools right now.",
    "Our data science team is particularly interested in leveraging machine learning to personalize our user experience.",
    "What are some of the AI/ML solutions that Google Cloud offers?",
    "Thank you, this has been very informative. We'll review the information and get back to you with any further questions."
]


async def send_transcript():
    """Connects to the WebSocket server and sends a series of mock transcripts."""
    uri = "ws://localhost:8080/ws/test_text"
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to the test endpoint. Sending mock transcripts...")

            for transcript in MOCK_TRANSCRIPTS:
                # Send the transcript to the server
                await websocket.send(transcript)
                print(f"Sent: {transcript}")

                # Wait for and print the response from the server
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    response_data = json.loads(response)
                    print(f"Received: {json.dumps(response_data, indent=2)}")
                except asyncio.TimeoutError:
                    print("No response received within 10 seconds.")
                except websockets.exceptions.ConnectionClosed:
                    print("Connection closed by server.")
                    break
                
                # Add a delay to simulate a real-time conversation
                await asyncio.sleep(2)
            
            print("Finished sending all mock transcripts.")

    except (websockets.exceptions.ConnectionClosedError, ConnectionRefusedError) as e:
        print(f"Connection failed: {e}")
        print("Please ensure the main server is running (`uvicorn main:app --port 8080`).")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(send_transcript())
