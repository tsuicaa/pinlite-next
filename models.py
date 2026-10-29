from datetime import datetime

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey,
    Identity, Index, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True
    )
    email: Mapped[str] = mapped_column(
        Text, unique=True
    )
    display_name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('public', 'private')",
            name="collections_visbility_check",
        ),
        CheckConstraint(
            "parent_id IS NULL OR parent_id <> id",
            name="collections_parent_check",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True
    )
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("collections.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(
        Text, server_default=""
    )
    visibility: Mapped[str] = mapped_column(
        String(10), server_default="private"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

class Media(Base):
    __tablename__ = "media"
    __table_args__ = (
        CheckConstraint(
            """
            (storage_kind = 'external'
            AND external_url IS NOT NULL
            AND object_key IS NULL)
            OR
            (storage_kind = 'hosted'
            AND object_key IS NOT NULL
            AND external_url IS NULL)
            """,
            name="media_storage_check",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True
    )
    storage_kind: Mapped[str] = mapped_column(String(10))
    external_url: Mapped[str | None] = mapped_column(Text)
    object_key: Mapped[str | None] = mapped_column(
        Text, unique=True
    )
    thumbnail_key: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(
        String(64), unique=True
    )
    mime_type: Mapped[str | None] = mapped_column(String(100))
    width: Mapped[int | None]
    height: Mapped[int | None]
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

class Pin(Base):
    __tablename__ = "pins"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('public', 'private')",
            name="pins_visibility_check",
        ),
        Index("pins_visbility_id_index", "visibility", "id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True
    )
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    media_id: Mapped[int] = mapped_column(
        ForeignKey("media.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(
        Text, server_default=""
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(
        String(10), server_default="private"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

class CollectionPin(Base):
    __tablename__ = "collection_pins"
    __table_args__ = (
        Index(
            "collection_pins_feed_index",
            "collection_id", "created_at", "pin_id",
        ),
    )

    collection_id: Mapped[int] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"),
        primary_key=True,
    )
    pin_id: Mapped[int] = mapped_column(
        ForeignKey("pins.id", ondelete="CASCADE"),
        primary_key=True,
        index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )