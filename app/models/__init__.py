import secrets
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, Text
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, Relationship, SQLModel


class BusinessType(str, Enum):
    SHOP = "shop"
    EDUCATION = "education"
    SERVICE = "service"


class ResponseStyle(str, Enum):
    FRIENDLY = "friendly"
    FORMAL = "formal"
    BRIEF = "brief"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class EscalationStatus(str, Enum):
    PENDING = "pending"
    ANSWERED = "answered"
    CLOSED = "closed"


def _enum_column(enum_cls, **kwargs) -> Column:
    """Build a native PG enum column that stores the enum *value* (lowercase),
    matching the types created by the alembic migrations, instead of the
    default SQLAlchemy behaviour of storing the member *name* (uppercase)."""
    return Column(
        SAEnum(
            enum_cls,
            name=enum_cls.__name__.lower(),
            values_callable=lambda e: [member.value for member in e],
        ),
        **kwargs,
    )


class Business(SQLModel, table=True):
    __tablename__ = "businesses"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    type: BusinessType = Field(sa_column=_enum_column(BusinessType, nullable=False))
    field: str
    contact: str
    working_hours: str
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)

    api_key: str = Field(default_factory=lambda: secrets.token_urlsafe(32), unique=True, index=True)
    welcome_message: Optional[str] = None
    max_tokens: int = Field(default=1000)
    response_style: ResponseStyle = Field(
        default=ResponseStyle.FRIENDLY,
        sa_column=_enum_column(ResponseStyle, nullable=False, server_default="friendly"),
    )
    # Phone of the business owner; used to link a logged-in User (auth via OTP) to
    # the business they manage, and as the escalation/SMS destination.
    owner_phone: Optional[str] = Field(default=None, index=True)

    details: list["BusinessDetail"] = Relationship(back_populates="business")
    conversations: list["Conversation"] = Relationship(back_populates="business")


class BusinessDetail(SQLModel, table=True):
    __tablename__ = "business_details"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    business_id: uuid.UUID = Field(foreign_key="businesses.id", index=True)
    key: str
    value: str

    business: Optional[Business] = Relationship(back_populates="details")


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: str = Field(index=True)
    business_id: uuid.UUID = Field(foreign_key="businesses.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    business: Optional[Business] = Relationship(back_populates="conversations")
    messages: list["Message"] = Relationship(back_populates="conversation")


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    conversation_id: uuid.UUID = Field(foreign_key="conversations.id", index=True)
    role: MessageRole = Field(sa_column=_enum_column(MessageRole, nullable=False))
    content: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    conversation: Optional[Conversation] = Relationship(back_populates="messages")


class User(SQLModel, table=True):
    """A business owner who logs in with their phone number (OTP).

    Linked to the business they manage via ``business_id`` (resolved from
    ``Business.owner_phone`` at first login). The bearer token issued on login
    resolves to this row, and from here to the user's business."""

    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    phone: str = Field(unique=True, index=True)
    business_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="businesses.id", index=True
    )
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login_at: Optional[datetime] = None


class OtpCode(SQLModel, table=True):
    """A one-time verification code sent to a phone. The plaintext code is never
    stored — only a hash — and each code is single-use with a short expiry."""

    __tablename__ = "otp_codes"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    phone: str = Field(index=True)
    code_hash: str
    expires_at: datetime
    consumed: bool = False
    attempts: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FaqEntry(SQLModel, table=True):
    """An owner-defined question/answer pair. Injected into the system prompt as
    the agent's source of truth: the agent answers from these (plus the business
    profile), and escalates when a customer's question isn't covered."""

    __tablename__ = "faq_entries"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    business_id: uuid.UUID = Field(foreign_key="businesses.id", index=True)
    question: str = Field(sa_column=Column(Text, nullable=False))
    answer: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Escalation(SQLModel, table=True):
    """A customer question the agent couldn't answer from the business's knowledge.
    Created when the model emits the ``[NEED_HUMAN]`` marker; the owner is notified
    by SMS and can review/answer these from their dashboard."""

    __tablename__ = "escalations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    business_id: uuid.UUID = Field(foreign_key="businesses.id", index=True)
    conversation_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="conversations.id", index=True
    )
    question: str = Field(sa_column=Column(Text, nullable=False))
    status: EscalationStatus = Field(
        default=EscalationStatus.PENDING,
        sa_column=_enum_column(EscalationStatus, nullable=False, server_default="pending"),
    )
    answer: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    answered_at: Optional[datetime] = None


class AuthSession(SQLModel, table=True):
    """A server-side bearer token. Opaque (``secrets.token_urlsafe``), stored so
    it can be revoked, and resolved to a User on each authenticated request."""

    __tablename__ = "auth_sessions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    token: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32), unique=True, index=True
    )
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)
