import os
from urllib.parse import quote

from flask import Flask, jsonify, request
from sqlalchemy import select

from db import Session
from models import Media, Pin

app = Flask(__name__)

def media_url(key):
    base = os.environ.get("MEDIA_BASE_URL", "").rstrip("/")
    if not key or not base:
        return None
    return f"{base}/{quote(key, safe='/')}"

@app.get("/api/health")
def health():
    return jsonify(status="ok")

@app.get("/api/pins")
def public_pins():
    before = request.args.get("before")

    if before is not None:
        try:
            before = int(before)
            if not 0 < before <= 9223372036854775807:
                raise ValueError()
        except ValueError:
            return jsonify(error="Invalid pagination cursor"), 400

    query = (
        select(Pin, Media)
        .join(Media, Pin.media_id == Media.id)
        .where(Pin.visibility == "public")
        .order_by(Pin.id.desc())
        .limit(31)
    )

    if before is not None:
        query = query.where(Pin.id < before)

    with Session() as session:
        rows = session.execute(query).all()
        has_more = len(rows) > 30
        rows = rows[:30]

        pins = [
            {
                "id": str(pin.id),
                "title": pin.title,
                "description": pin.description,
                "source_url": pin.source_url,
                "image": (
                    media.external_url
                    if media.storage_kind == "external"
                    else media_url(media.object_key)
                ),
                "thumbnail": media_url(media.thumbnail_key),
                "mime_type": media.mime_type,
                "width": media.width,
                "height": media.height,
            }
            for pin, media in rows
        ]

    return jsonify(pins = pins, next_cursor=pins[-1]["id"] if has_more else None,)