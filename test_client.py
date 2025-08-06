import asyncio
import websockets
import json

async def send_transcript():
    """Connects to the WebSocket server and sends transcripts."""
    uri = "ws://localhost:8000/ws/test_text"  # Assumes the server runs on port 8000
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to the test endpoint. Type your transcript and press Enter.")
            print("Type 'exit' to quit.")

            while True:
                # Get transcript from user input
                transcript = input("> ")
                if transcript.lower() == 'exit':
                    break

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


    except (websockets.exceptions.ConnectionClosedError, ConnectionRefusedError) as e:
        print(f"Connection failed: {e}")
        print("Please ensure the main server is running (`uvicorn main:app`).")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(send_transcript())
