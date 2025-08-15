import asyncio
import json
import uuid
from fastapi import WebSocket
import google.genai as genai
from google.genai import types

from config import logger

# --- Gemini Tool Definitions ---
extract_fact_function = {
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
                "description": "The category of the fact. Must be 'infrastructure' for infrastructure components (e.g., 'EC2', 'S3', 'VPC'), 'goals' for business or technical goals, 'concerns' for any stated problems or challenges, or 'other' for all other facts."
            },
            "gcp_service": {
                "type": "string",
                "description": "The equivalent GCP service for an infrastructure fact. Only provide if the category is 'infrastructure' and a clear equivalent exists."
            }
        },
        "required": ["fact", "category"]
    }
}

provide_tip_function = {
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
}

answer_question_function = {
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

google_search_function = {
    "name": "google_search",
    "description": "Search Google for information.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query."
            }
        },
        "required": ["query"]
    }
}

tools = types.Tool(function_declarations=[
    extract_fact_function,
    provide_tip_function,
    answer_question_function,
    google_search_function
])
grounding_tool = types.Tool(
    google_search=types.GoogleSearch()
)

config = types.GenerateContentConfig(tools=[tools])


# --- Gemini System Prompt ---
SYSTEM_PROMPT = """
You are a highly advanced AI assistant for a Google Cloud Customer Engineer (CE).
You are listening in on a live sales call. Your purpose is to provide real-time support.
For each user transcript you receive, you must use the provided tools to respond.

Your primary goal is to help the CE. Therefore, you should always look for opportunities to `provide_tip`.
- `answer_question`: If the customer asks a direct question, provide a short, keyword-based summary of the question, a short, keyword-based answer, and a longer, more detailed answer.
- `provide_tip`:  Identify a key customer statement and suggest a specific question or topic the CE should raise. The tip should be short, actionable, and keyword-based. For example: "Customer mentioned X, ask about Y. also include a longer version: Provide a detailed, comprehensive response that expands on the tip. This version should not just suggest a topic but should actually explain the relevant concepts and how they apply. The goal is to give the CE all the necessary information to talk about the topic confidently and knowledgably. For example, if the tip suggests talking about Google Cloud's AI/ML portfolio, the longer version should explain what that portfolio includes (e.g., Vertex AI, specific APIs) and provide concrete examples of how these tools can embed intelligence in a customer's products and processes, linking to whats been said before. Do not repeat information from the short tip in the long tip. Start with the specific questions first meant be read verbatim, seperated by newline followed by the explaination
- `extract_fact`: If a key fact is mentioned (a number, technology, pethrson, or goal), categorize it as either 'infrastructure' or 'other'. If the category is 'infrastructure', provide the equivalent GCP service if one exists. Facts should be concise and to the point. For example, instead of "The entire infrastructure is on AWS", say "100% AWS". Instead of "Their application is built with React", say "React". facts should also usually trigger provide_tip
If you have no valuable information to provide, do not call any tool.
"""

async def send_to_gemini(ws: WebSocket, client, chat_history, transcript: str):
    logger.info(f"Sending to Gemini: {transcript}")

    try:
        chat_history.append({'role': 'user', 'parts': [{'text': transcript}]})

        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=chat_history,
            config=config,
        )

        if not response.candidates or not response.candidates[0].content.parts:
            logger.info("Gemini returned no response, skipping.")
            await ws.send_text(json.dumps({"response_type": "STATUS", "payload": "Gemini returned no response."}))
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

        chat_history.append(response.candidates[0].content)

        if not function_called:
            logger.info("Gemini did not call a function.")
            await ws.send_text(json.dumps({"response_type": "STATUS", "payload": "Gemini returned no response."}))

    except Exception as e:
        logger.error(f"Error sending to Gemini: {e}")
