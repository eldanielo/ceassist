import requests
import json
import uuid

BASE_URL = "http://localhost:8000"
APP_NAME = "agent"
USER_ID = "test_user"

def main():
    """
    Creates a session and allows interactive messaging with the agent.
    """
    session_id = f"test_session_{uuid.uuid4()}"
    session_url = f"{BASE_URL}/apps/{APP_NAME}/users/{USER_ID}/sessions/{session_id}"

    print(f"Creating session: {session_id}...")
    try:
        response = requests.post(session_url)
        response.raise_for_status()
        print("Session created successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Error creating session: {e}")
        return

    print("\nEnter a message to send to the agent (type 'exit' to quit):")

    while True:
        try:
            message = input("> ")
            if message.lower() == 'exit':
                break

            data = {
                "app_name": APP_NAME,
                "user_id": USER_ID,
                "session_id": session_id,
                "new_message": {
                    "role": "user",
                    "parts": [{"text": message}]
                }
            }

            run_url = f"{BASE_URL}/run"
            run_response = requests.post(run_url, json=data)
            run_response.raise_for_status()

            # Print the full JSON response
            print("\n--- Full Agent Response ---")
            response_json = run_response.json()
            print(json.dumps(response_json, indent=2))
            print("---------------------------\n")

            # Print just the function call and data
            print("--- Function Call Summary ---")
            summary_found = False
            if isinstance(response_json, list):
                for event in response_json:
                    part = event.get("content", {}).get("parts", [{}])[0]
                    
                    # Check for the model's function call
                    if "functionCall" in part:
                        summary_found = True
                        function_call = part["functionCall"]
                        print(f"Function call: {function_call.get('name')}")
                        print(f"Args: {json.dumps(function_call.get('args', {}), indent=4)}")
                        print("-" * 10)

                    # Check for the tool's function response
                    if "functionResponse" in part:
                        summary_found = True
                        function_response = part["functionResponse"]
                        print(f"Function response from: {function_response.get('name')}")
                        print(f"Payload: {json.dumps(function_response.get('response', {}), indent=4)}")
                        print("-" * 10)

            if not summary_found:
                print("No function calls or responses found in the agent's output.")
            print("---------------------------\n")

        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
        except json.JSONDecodeError:
            print("Could not decode JSON response.")
            print(f"Raw response: {run_response.text}")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            break

if __name__ == "__main__":
    main()