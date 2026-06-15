from openai import OpenAI
import shelve
from dotenv import load_dotenv
import os
import logging

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
client = OpenAI(api_key=OPENAI_API_KEY)

# System prompt that gives the assistant its persona/behavior. With the
# Assistants API this lived on the Assistant object; with the Responses API we
# pass it as `instructions` on every call.
ASSISTANT_INSTRUCTIONS = (
    "You're a Mexican best friend, to the user, who speaks in Mexican Spanish "
    "The user speaks mainly in English, but still practices Spanish when speaking with you."
    "Only text the user in Mexican Spanish until the user messes up their Spanish Grammar; "
    "Once the user messes up their Mexican Spanish Grammar, you are to respond shortly, in English, "
    "how the user can improve their Spanish from their previous message, and then continue the conversation in Spanish. "
)


# Use a context manager to ensure the shelf file is closed properly.
# The Responses API keeps conversation state server-side: instead of storing a
# thread_id, we store the id of the last response and chain new turns to it via
# `previous_response_id`.
def check_if_response_exists(wa_id):
    with shelve.open("responses_db") as responses_shelf:
        return responses_shelf.get(wa_id, None)


def store_response(wa_id, response_id):
    with shelve.open("responses_db", writeback=True) as responses_shelf:
        responses_shelf[wa_id] = response_id


def generate_response(message_body, wa_id, name):
    # Retrieve the id of this user's previous response (if any) so the model
    # has the prior conversation as context.
    previous_response_id = check_if_response_exists(wa_id)

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
        # A stale/invalid previous_response_id (e.g. left over from the old
        # Assistants threads) would fail; retry as a fresh conversation.
        logging.warning(f"Falling back to a new conversation for {wa_id}: {e}")
        response = client.responses.create(
            model=OPENAI_MODEL,
            instructions=ASSISTANT_INSTRUCTIONS,
            input=message_body,
        )

    # Persist this response id so the next message continues the thread.
    store_response(wa_id, response.id)

    new_message = response.output_text
    logging.info(f"Generated message: {new_message}")
    return new_message