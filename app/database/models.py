from datetime import datetime
from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    TIMESTAMP,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "user"

    id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    email = Column(Text, nullable=False, unique=True)
    email_verified = Column(Boolean, nullable=False, default=False)
    image = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now())

    sessions = relationship("Session", back_populates="user", cascade="all, delete")
    accounts = relationship("Account", back_populates="user", cascade="all, delete")
    settings = relationship("Settings", back_populates="user", uselist=False, cascade="all, delete")
    encrypted_mails = relationship("EncryptedMail", back_populates="user", cascade="all, delete")


class EncryptedMail(Base):
    __tablename__ = "encrypted_mail"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column("userId", Text, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    gmail_message_id = Column("gmail_message_id", Text, nullable=False)
    ciphertext = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    categories = Column(ARRAY(Text), nullable=True)
    priority = Column(ARRAY(Numeric(precision=10, scale=4)), nullable=False, server_default="{}")
    version = Column(ARRAY(Text), nullable=False, server_default="{}")
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now())

    user = relationship("User", back_populates="encrypted_mails")

    __table_args__ = (
        UniqueConstraint("userId", "gmail_message_id", name="encrypted_mail_user_message_uq"),
        Index("encrypted_mail_user_idx", "userId"),
    )


class Category(Base):
    __tablename__ = "categories"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    name = Column(Text, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    examples = Column(JSONB, nullable=True, server_default="[]")


class Settings(Base):
    __tablename__ = "settings"

    id = Column(Text, primary_key=True)
    models_list = Column("models", ARRAY(Text), server_default="{}")
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    user_id = Column("userId", Text, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, unique=True)

    user = relationship("User", back_populates="settings")
    models = relationship("Model", back_populates="setting", cascade="all, delete")


class Model(Base):
    __tablename__ = "models"

    id = Column(Text, primary_key=True)
    name = Column(Text, nullable=False)
    provider = Column("provider", Text, nullable=False)
    api_key = Column("api_key", Text, nullable=False)
    setting_id = Column("setting_id", Text, ForeignKey("settings.id", ondelete="CASCADE"), nullable=False)

    setting = relationship("Settings", back_populates="models")


class Session(Base):
    __tablename__ = "session"

    id = Column(Text, primary_key=True)
    expires_at = Column("expires_at", TIMESTAMP, nullable=False)
    token = Column(Text, nullable=False, unique=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    ip_address = Column("ip_address", Text, nullable=True)
    user_agent = Column("user_agent", Text, nullable=True)
    user_id = Column("user_id", Text, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)

    user = relationship("User", back_populates="sessions")

    __table_args__ = (Index("session_user_id_idx", "user_id"),)


class Account(Base):
    __tablename__ = "account"

    id = Column(Text, primary_key=True)
    account_id = Column("account_id", Text, nullable=False)
    provider_id = Column("provider_id", Text, nullable=False)
    user_id = Column("user_id", Text, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    access_token = Column("access_token", Text, nullable=True)
    refresh_token = Column("refresh_token", Text, nullable=True)
    id_token = Column("id_token", Text, nullable=True)
    access_token_expires_at = Column("access_token_expires_at", TIMESTAMP, nullable=True)
    refresh_token_expires_at = Column("refresh_token_expires_at", TIMESTAMP, nullable=True)
    scope = Column(Text, nullable=True)
    password = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now())

    user = relationship("User", back_populates="accounts")

    __table_args__ = (
        Index("account_user_id_idx", "user_id"),
        Index("account_provider_idx", "provider_id", "account_id"),
    )


class Verification(Base):
    __tablename__ = "verification"

    id = Column(Text, primary_key=True)
    identifier = Column(Text, nullable=False)
    value = Column(Text, nullable=False)
    expires_at = Column("expires_at", TIMESTAMP, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
