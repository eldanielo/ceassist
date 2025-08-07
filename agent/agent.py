from typing import Optional
from google.adk.agents import Agent


# --- ADK Tool Definitions ---


def extract_fact(
    fact: Optional[str] = None,
    category: Optional[str] = None,
    gcp_service: Optional[str] = None,
):
    """
    Extract a key fact from the transcript.

    Args:
        fact: The key fact, such as a number, technology, person, or goal. Should be keywords only.
        category: The category of the fact. Must be 'infrastructure' for infrastructure components (e.g., 'EC2', 'S3', 'VPC') or 'other' for all other facts.
        gcp_service: The equivalent GCP service for an infrastructure fact. Only provide if the category is 'infrastructure' and a clear equivalent exists.
    """
    return {
        "response_type": "FACT",
        "payload": {"fact": fact, "category": category, "gcp_service": gcp_service},
    }


def provide_tip(short_tip: Optional[str] = None, long_tip: Optional[str] = None):
    """
    Provide a proactive tip for the Customer Engineer.

    Args:
        short_tip: A short, keyword-based version of the tip.
        long_tip: A longer, more detailed version of the tip.
    """
    return {
        "response_type": "TIP",
        "payload": {"short": f"💡 {short_tip}", "long": long_tip},
    }


def answer_question(
    question: Optional[str] = None,
    short_answer: Optional[str] = None,
    long_answer: Optional[str] = None,
):
    """
    Answer a direct question from the customer.

    Args:
        question: A short, keyword-based summary of the customer's question.
        short_answer: A short, keyword-based answer to the customer's question.
        long_answer: A longer, more detailed answer to the customer's question.
    """
    return {
        "response_type": "ANSWER",
        "payload": {"question": question, "short": short_answer, "long": long_answer},
    }

TOOLS = [extract_fact, provide_tip, answer_question]

# --- Gemini System Prompt ---
SYSTEM_PROMPT = """
You are a highly advanced AI assistant for a Google Cloud Customer Engineer (CE).
You are listening in on a live sales call. Your purpose is to provide real-time support.
For each user transcript you receive, you must use the provided tools to respond.

Your primary goal is to help the CE. Therefore, you should always look for opportunities to `provide_tip`.
- `answer_question`: If the customer asks a direct question, provide a short, keyword-based summary of the question, a short, keyword-based answer, and a longer, more detailed answer.
- `provide_tip`: If there is an opportunity for the CE to ask a question or position a product. This is your most important function. Tips should be short and keyword-based, but you should also provide a longer, more detailed version.
- `extract_fact`: If a key fact is mentioned (a number, technology, person, or goal), categorize it as either 'infrastructure' or 'other'. If the category is 'infrastructure', provide the equivalent GCP service if one exists. Facts should be concise and to the point. For example, instead of "The entire infrastructure is on AWS", say "100% AWS". Instead of "Their application is built with React", say "React". facts should also usually trigger provide_tip
If you have no valuable information to provide, do not call any tool. Dont respond outside of the tools.
"""
root_agent = Agent(
    name="ceassist",
    model="gemini-2.0-flash",
    description=(
        "Agent to answer questions about the time and weather in a city."
    ),
    instruction=SYSTEM_PROMPT,
    tools=TOOLS,
)