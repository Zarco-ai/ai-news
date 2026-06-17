from openai import OpenAI
from dotenv import load_dotenv
import os
import logging
from dataclasses import dataclass

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# Default to the cheap model; override with OPENAI_MODEL in the environment.
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
client = OpenAI(api_key=OPENAI_API_KEY)

# System prompt that gives the assistant its persona/behavior. With the
# Assistants API this lived on the Assistant object; with the Responses API we
# pass it as `instructions` on every call.
ASSISTANT_INSTRUCTIONS = (
    "You're a Mexican best friend, to the user, who is trying to speak in Mexican Spanish "
    "The user speaks mainly in English, but still practices Spanish when speaking with you."
    "Only text the user in Mexican Spanish until the user messes up their Spanish Grammar; "
    "Once the user messes up their Mexican Spanish Grammar, you are to respond, in English, "
    "how the user can improve their Spanish from their previous message (e.g. grammar, conjugation), and then continue the conversation in Spanish. "
    "If the user sends a message in English, in your response; simply add a translation, at the begining, to what their English message should look like in Mexican Spanish,"
    "along with the other information required in your response."

)


@dataclass
class AssistantReply:
    """Result of one OpenAI call: the text plus the data we persist."""

    text: str
    response_id: str
    input_tokens: int
    output_tokens: int


def generate_response(message_body, wa_id, name, previous_response_id=None):
    """Generate the tutor's reply.

    Conversation continuity is provided by `previous_response_id` (stored on the
    Conversation row in Postgres), so this function no longer touches local disk.
    Returns an AssistantReply with the text, the new response id to persist, and
    token usage for cost tracking.
    """
    if previous_response_id is None:
        logging.info(f"Starting new conversation for {name} with wa_id {wa_id}")
    else:
        logging.info(f"Continuing conversation for {name} with wa_id {wa_id}")

    try:
        response = client.responses.create(
            model=OPENAI_MODEL,
            instructions=ASSISTANT_INSTRUCTIONS,
            input=message_body,
            previous_response_id=previous_response_id,
        )
    except Exception as e:
        # A stale/invalid previous_response_id would fail; retry as a fresh
        # conversation so a broken pointer never blocks the user.
        logging.warning(f"Falling back to a new conversation for {wa_id}: {e}")
        response = client.responses.create(
            model=OPENAI_MODEL,
            instructions=ASSISTANT_INSTRUCTIONS,
            input=message_body,
        )

    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0

    new_message = response.output_text
    logging.info(f"Generated message: {new_message}")
    return AssistantReply(
        text=new_message,
        response_id=response.id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
