"""SQLAlchemy models for the WhatsApp AI Spanish tutor.

The schema is organized in the layers the app cares about:

- Agent       -> identity of the WhatsApp number acting as the tutor (PHONE_NUMBER_ID)
- User        -> the people who text the tutor (identity)
- Conversation-> a chat session between one user and one agent (session state)
- Message     -> every inbound/outbound message (source of truth for history)
- WebhookEvent-> raw webhook deliveries, used for idempotency/debugging (reliability)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Agent(Base):
    """A WhatsApp number that acts as the AI tutor.

    `phone_number_id` is the Meta `PHONE_NUMBER_ID` so you always know which
    number replied (e.g. the ai_spanish_tutor).
    """

    __tablename__ = "agents"

    phone_number_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), default="ai_spanish_tutor")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    conversations: Mapped[list[Conversation]] = relationship(back_populates="agent")


class User(Base):
    """A person who texts the tutor, identified by their WhatsApp id (wa_id)."""

    __tablename__ = "users"

    wa_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile_name: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    conversations: Mapped[list[Conversation]] = relationship(back_populates="user")
    messages: Mapped[list[Message]] = relationship(back_populates="user")


class Conversation(Base):
    """A chat session between one user and one agent (tutor number)."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_wa_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.wa_id"), index=True
    )
    agent_phone_number_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("agents.phone_number_id"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="active")
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    # OpenAI Responses API conversation pointer. Stored here (not in a local
    # file) so conversation memory survives deploys/restarts and works across
    # multiple gunicorn workers.
    last_response_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="conversations")
    agent: Mapped[Agent] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(back_populates="conversation")


class Message(Base):
    """A single inbound or outbound message in a conversation."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id"), index=True
    )
    user_wa_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.wa_id"), index=True
    )
    # WhatsApp message id (wamid). Unique so duplicate webhook deliveries
    # cannot insert the same inbound message twice. Null for outbound replies
    # whose id we don't track.
    wa_message_id: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True
    )
    direction: Mapped[str] = mapped_column(String(16))  # inbound | outbound
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    message_type: Mapped[str] = mapped_column(String(32), default="text")
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    user: Mapped[User] = relationship(back_populates="messages")


class WebhookEvent(Base):
    """Raw webhook deliveries from Meta.

    `event_key` is a stable identifier for the delivery (the message wamid for
    incoming messages, or the status id for status updates) so the same webhook
    retry is not processed twice.
    """

    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(32), default="unknown")
    phone_number_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ApiUsage(Base):
    """One row per OpenAI API call: tokens and computed USD cost.

    This is the source of truth for both the per-user daily limit and the
    global spend cap, and it lets you see per-user/day cost directly in TablePlus.
    """

    __tablename__ = "api_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wa_id: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(64), default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # Speeds up the per-user daily-limit query (wa_id + created_at range).
    __table_args__ = (Index("ix_api_usage_wa_id_created_at", "wa_id", "created_at"),)
