import logging
from flask import current_app, jsonify
import json
import requests

from app.services.openai_service import generate_response
from app.db.session import get_session
from app.db.repository import ChatRepository
from app.db.models import Conversation
import re


def log_http_response(response):
    logging.info(f"Status: {response.status_code}")
    logging.info(f"Content-type: {response.headers.get('content-type')}")
    logging.info(f"Body: {response.text}")


def get_text_message_input(recipient, text):
    return json.dumps(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
    )


#def generate_response(response):
    # Return text in uppercase
    #return response.upper()


def send_message(data):
    headers = {
        "Content-type": "application/json",
        "Authorization": f"Bearer {current_app.config['ACCESS_TOKEN']}",
    }

    url = f"https://graph.facebook.com/{current_app.config['VERSION']}/{current_app.config['PHONE_NUMBER_ID']}/messages"

    try:
        response = requests.post(
            url, data=data, headers=headers, timeout=10
        )  # 10 seconds timeout as an example
        response.raise_for_status()  # Raises an HTTPError if the HTTP request returned an unsuccessful status code
    except requests.Timeout:
        logging.error("Timeout occurred while sending message")
        return jsonify({"status": "error", "message": "Request timed out"}), 408
    except (
        requests.RequestException
    ) as e:  # This will catch any general request exception
        logging.error(f"Request failed due to: {e}")
        return jsonify({"status": "error", "message": "Failed to send message"}), 500
    else:
        # Process the response as normal
        log_http_response(response)
        return response


def process_text_for_whatsapp(text):
    # Remove brackets
    pattern = r"\【.*?\】"
    # Substitute the pattern with an empty string
    text = re.sub(pattern, "", text).strip()

    # Pattern to find double asterisks including the word(s) in between
    pattern = r"\*\*(.*?)\*\*"

    # Replacement pattern with single asterisks
    replacement = r"*\1*"

    # Substitute occurrences of the pattern with the replacement
    whatsapp_style_text = re.sub(pattern, replacement, text)

    return whatsapp_style_text


def _compute_cost_usd(input_tokens, output_tokens):
    """USD cost of a call from token counts and the configured per-1M rates."""
    input_rate = current_app.config["INPUT_COST_PER_1M"]
    output_rate = current_app.config["OUTPUT_COST_PER_1M"]
    return (input_tokens / 1_000_000) * input_rate + (
        output_tokens / 1_000_000
    ) * output_rate


def _send_text(wa_id, text):
    """Format for WhatsApp and send a plain text reply to a user."""
    data = get_text_message_input(wa_id, process_text_for_whatsapp(text))
    send_message(data)


# Age gate replies and the words we accept as a yes/no to "are you 18+?".
AGE_PROMPT = (
    "Hi! Before we start: are you 18 years or older? Reply YES to continue. "
    "(Hola, antes de empezar: ¿tienes 18 anos o mas? Responde SI para continuar.)"
)
AGE_WELCOME = (
    "Great, thanks! Let's start practicing your Spanish. "
    "(Perfecto, gracias. Empecemos a practicar tu espanol.)"
)
AGE_DECLINED = (
    "Sorry, you must be 18 or older to use this tutor. "
    "(Lo siento, debes tener 18 anos o mas para usar este tutor.)"
)

_AGE_YES = {
    "yes", "yeah", "yep", "yup", "y", "sure", "ok", "okay",
    "si", "sí", "claro", "sip", "18", "i'm 18", "im 18",
}
_AGE_NO = {"no", "nope", "nah", "n", "under 18", "menor"}


def _normalize(text):
    return (text or "").strip().lower()


def _is_affirmative_age(text):
    t = _normalize(text)
    return t in _AGE_YES or "18 or older" in t or "older than 18" in t


def _is_negative_age(text):
    t = _normalize(text)
    return t in _AGE_NO or "under 18" in t or "younger" in t


def process_whatsapp_message(body):
    wa_id = body["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"]
    name = body["entry"][0]["changes"][0]["value"]["contacts"][0]["profile"]["name"]

    message = body["entry"][0]["changes"][0]["value"]["messages"][0]
    message_body = message["text"]["body"]
    wa_message_id = message.get("id")
    message_type = message.get("type", "text")

    # The number acting as the ai_spanish_tutor (from .env via app config).
    phone_number_id = current_app.config["PHONE_NUMBER_ID"]
    spend_cap = current_app.config["GLOBAL_SPEND_CAP_USD"]
    per_user_limit = current_app.config["PER_USER_DAILY_LIMIT"]

    # Persist the inbound turn and decide whether we're allowed to answer.
    # If this exact webhook (wamid) was already processed, skip everything so
    # Meta retries don't double-reply.
    with get_session() as session:
        repo = ChatRepository(session)

        is_new = repo.record_webhook_event(
            event_key=wa_message_id or f"no-id:{hash(json.dumps(body))}",
            event_type="message",
            payload=json.dumps(body),
            phone_number_id=phone_number_id,
        )
        if not is_new:
            logging.info(f"Duplicate webhook for message {wa_message_id}; skipping.")
            return

        repo.upsert_agent(phone_number_id)
        user = repo.upsert_user(wa_id, name)
        conversation = repo.get_or_create_conversation(wa_id, phone_number_id)

        repo.record_message(
            conversation=conversation,
            user_wa_id=wa_id,
            direction="inbound",
            role="user",
            content=message_body,
            message_type=message_type,
            wa_message_id=wa_message_id,
        )

        conversation_id = conversation.id
        previous_response_id = conversation.last_response_id

        # Age gate (self-attested 18+). Unconfirmed users never reach OpenAI.
        age_status = None
        if not user.age_confirmed:
            if _is_affirmative_age(message_body):
                repo.confirm_age(user)
                age_status = "just_confirmed"
            elif _is_negative_age(message_body):
                age_status = "declined"
            else:
                age_status = "prompt"

        # Budget gates (checked before spending any OpenAI tokens).
        block_reason = None
        if repo.total_spend_usd() >= spend_cap:
            block_reason = "spend_cap"
        elif repo.count_user_messages_today(wa_id) >= per_user_limit:
            block_reason = "user_limit"

    # Handle the age gate first: confirm, decline, or (re)prompt. In every case
    # we stop here without calling OpenAI.
    if age_status == "just_confirmed":
        logging.info(f"User {wa_id} confirmed age 18+.")
        _send_text(wa_id, AGE_WELCOME)
        return
    if age_status == "declined":
        logging.info(f"User {wa_id} declined age confirmation.")
        _send_text(wa_id, AGE_DECLINED)
        return
    if age_status == "prompt":
        logging.info(f"Prompting {wa_id} for age confirmation.")
        _send_text(wa_id, AGE_PROMPT)
        return

    # If blocked, tell the user politely and stop (no OpenAI call).
    if block_reason == "spend_cap":
        logging.warning("Global spend cap reached; pausing OpenAI replies.")
        _send_text(
            wa_id,
            "The tutor is taking a short break right now. Please try again later.",
        )
        return
    if block_reason == "user_limit":
        logging.info(f"Daily limit reached for {wa_id}.")
        _send_text(
            wa_id,
            "You've reached today's practice limit. Let's continue tomorrow!",
        )
        return

    # OpenAI Integration (Responses API). Context comes from the stored
    # previous_response_id, not a local file.
    reply = generate_response(message_body, wa_id, name, previous_response_id)
    cost_usd = _compute_cost_usd(reply.input_tokens, reply.output_tokens)

    # Reply to the person who messaged us (wa_id), not a fixed recipient.
    _send_text(wa_id, reply.text)

    # Persist the assistant's reply, the conversation pointer, and the cost.
    with get_session() as session:
        repo = ChatRepository(session)
        conversation = repo.session.get(Conversation, conversation_id)
        repo.record_message(
            conversation=conversation,
            user_wa_id=wa_id,
            direction="outbound",
            role="assistant",
            content=process_text_for_whatsapp(reply.text),
            message_type="text",
            status="sent",
        )
        repo.set_last_response_id(conversation, reply.response_id)
        repo.record_api_usage(
            wa_id=wa_id,
            model=current_app.config["OPENAI_MODEL"],
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
            cost_usd=cost_usd,
        )


def is_valid_whatsapp_message(body):
    """
    Check if the incoming webhook event has a valid WhatsApp message structure.
    """
    return (
        body.get("object")
        and body.get("entry")
        and body["entry"][0].get("changes")
        and body["entry"][0]["changes"][0].get("value")
        and body["entry"][0]["changes"][0]["value"].get("messages")
        and body["entry"][0]["changes"][0]["value"]["messages"][0]
    )
