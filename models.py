from datetime import datetime

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey,
    Identity, Index, String, Text, func, Computed,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import TSVECTOR

from db import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True
    )
    email: Mapped[str] = mapped_column(
        Text, unique=True
    )
    password_hash: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(String(100))
    is_admin: Mapped[bool] = mapped_column(server_default="false")
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
        Index("collections_owner_import_key_index", "owner_id", "import_key", unique=True),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(), primary_key=True
    )
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"),
        index=True,
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
    import_key: Mapped[str | None] = mapped_column(Text)

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
    discovery_labels: Mapped[str | None] = mapped_column(Text)
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
        Index("pins_search_index", "search_document", postgresql_using="gin"),
        Index("pins_creator_import_key_index", "creator_id", "import_key", unique=True),
        CheckConstraint(
            "NOT moderation_hold OR visibility = 'private'",
                name="pins_moderation_hold_check",
        ),
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
    search_document: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple'::regconfig, title || ' ' || description)",
            persisted=True
        ),
    )
    import_key: Mapped[str | None] = mapped_column(Text)

    moderation_hold: Mapped[bool] = mapped_column(server_default="false")

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

class RequestLimit(Base):
    __tablename__ = "request_limits"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window: Mapped[int] = mapped_column(BigInteger)
    count: Mapped[int]

class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        Index(
            "tags_search_index",
            "search_document",
            postgresql_using="gin",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    search_document: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple'::regconfig, name)",
            persisted=True,
        ),
    )

class PinTag(Base):
    __tablename__ = "pin_tags"

    pin_id: Mapped[int] = mapped_column(
        ForeignKey("pins.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )

class PinReport(Base):
    __tablename__ = "pin_reports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'dismissed', 'actioned')",
            name="pin_reports_status_check",
        ),
        Index("pin_reports_queue_index", "status", "created_at"),
    )

    pin_id: Mapped[int] = mapped_column(
        ForeignKey("pins.id", ondelete="CASCADE"), primary_key=True,
    )
    reporter_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True,
    )
    reason: Mapped[str] = mapped_column(String(32))
    note: Mapped[str] = mapped_column(Text, server_default="")
    status: Mapped[str] = mapped_column(String(16), server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )