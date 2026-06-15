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


def process_whatsapp_message(body):
    wa_id = body["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"]
    name = body["entry"][0]["changes"][0]["value"]["contacts"][0]["profile"]["name"]

    message = body["entry"][0]["changes"][0]["value"]["messages"][0]
    message_body = message["text"]["body"]
    wa_message_id = message.get("id")
    message_type = message.get("type", "text")

    # The number acting as the ai_spanish_tutor (from .env via app config).
    phone_number_id = current_app.config["PHONE_NUMBER_ID"]

    # Persist the inbound turn. If this exact webhook (wamid) was already
    # processed, skip everything so Meta retries don't double-reply.
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
        repo.upsert_user(wa_id, name)
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

    # OpenAI Integration (Responses API)
    response = generate_response(message_body, wa_id, name)
    response = process_text_for_whatsapp(response)

    # Reply to the person who messaged us (wa_id), not a fixed recipient.
    data = get_text_message_input(wa_id, response)
    send_message(data)

    # Persist the assistant's reply.
    with get_session() as session:
        repo = ChatRepository(session)
        conversation = repo.session.get(Conversation, conversation_id)
        repo.record_message(
            conversation=conversation,
            user_wa_id=wa_id,
            direction="outbound",
            role="assistant",
            content=response,
            message_type="text",
            status="sent",
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
