"""CRUD repository for the WhatsApp AI tutor tables.

`ChatRepository` is the single API the webhook flow uses to persist a turn:
upsert the agent + user, find/create their conversation, and record each
message. It also records raw webhook events so duplicate deliveries from Meta
are processed only once.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Agent, Conversation, Message, User, WebhookEvent


class ChatRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- identity -------------------------------------------------------

    def upsert_agent(self, phone_number_id: str, display_name: str = "ai_spanish_tutor") -> Agent:
        """Ensure the tutor's WhatsApp number (PHONE_NUMBER_ID) exists."""
        agent = self.session.get(Agent, phone_number_id)
        if agent is None:
            agent = Agent(phone_number_id=phone_number_id, display_name=display_name)
            self.session.add(agent)
            self.session.flush()
        elif display_name and agent.display_name != display_name:
            agent.display_name = display_name
        return agent

    def upsert_user(self, wa_id: str, profile_name: str = "") -> User:
        """Ensure the texting user exists; refresh their profile name."""
        user = self.session.get(User, wa_id)
        if user is None:
            user = User(wa_id=wa_id, profile_name=profile_name)
            self.session.add(user)
            self.session.flush()
        elif profile_name and user.profile_name != profile_name:
            user.profile_name = profile_name
        return user

    # --- sessions -------------------------------------------------------

    def get_or_create_conversation(
        self, user_wa_id: str, agent_phone_number_id: str
    ) -> Conversation:
        """Return the active conversation for this user+agent, or start one."""
        stmt = (
            select(Conversation)
            .where(
                Conversation.user_wa_id == user_wa_id,
                Conversation.agent_phone_number_id == agent_phone_number_id,
                Conversation.status == "active",
            )
            .order_by(Conversation.last_message_at.desc())
            .limit(1)
        )
        conversation = self.session.scalars(stmt).first()
        if conversation is None:
            conversation = Conversation(
                user_wa_id=user_wa_id,
                agent_phone_number_id=agent_phone_number_id,
            )
            self.session.add(conversation)
            self.session.flush()
        return conversation

    # --- messages -------------------------------------------------------

    def record_message(
        self,
        *,
        conversation: Conversation,
        user_wa_id: str,
        direction: str,
        role: str,
        content: str,
        message_type: str = "text",
        wa_message_id: str | None = None,
        status: str | None = None,
    ) -> Message:
        """Insert one message and bump the conversation's activity counters."""
        message = Message(
            conversation_id=conversation.id,
            user_wa_id=user_wa_id,
            wa_message_id=wa_message_id,
            direction=direction,
            role=role,
            message_type=message_type,
            content=content,
            status=status,
        )
        self.session.add(message)
        conversation.message_count += 1
        conversation.last_message_at = datetime.now(timezone.utc)
        self.session.flush()
        return message

    # --- reliability ----------------------------------------------------

    def record_webhook_event(
        self,
        *,
        event_key: str,
        event_type: str,
        payload: str,
        phone_number_id: str | None = None,
    ) -> bool:
        """Record a webhook delivery. Returns True if it's new, False if a
        duplicate (already processed) so the caller can skip re-processing."""
        existing = self.session.scalar(
            select(WebhookEvent).where(WebhookEvent.event_key == event_key)
        )
        if existing is not None:
            return False
        self.session.add(
            WebhookEvent(
                event_key=event_key,
                event_type=event_type,
                payload=payload,
                phone_number_id=phone_number_id,
            )
        )
        self.session.flush()
        return True
