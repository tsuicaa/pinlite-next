import os
from urllib.parse import quote, urlsplit
from datetime import timedelta, datetime, timezone

from flask import Flask, jsonify, request, session as login_session
from sqlalchemy import delete, select, func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert
from werkzeug.security import generate_password_hash, check_password_hash

from db import Session
from models import Collection, CollectionPin, Media, Pin, User, RequestLimit, Tag, PinTag, PinReport

from uuid import uuid4
from images import prepare_image
from storage import image_url, put_image, delete_images

import click

from quotas import check_quota, QuotaExceeded, account_usage, check_quota, PIN_LIMIT
from limits import check_limit

from tags import get_tags, normalize_tags, replace_tags

from pinterest_boards import BoardPreviewError, BoardURLError, preview_board, board_path, board_pin_page

from hashlib import sha256

import json

DUMMY_PASSWORD_HASH = generate_password_hash("login-placeholder")

app = Flask(__name__, static_folder="public", static_url_path="/static")
app.config.update(
    SECRET_KEY=os.environ["SECRET_KEY"],
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)

def media_url(key):
    return image_url(key)

def serialize_pin(pin, media):
    return {
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
        "visibility": pin.visibility,
        "moderation_hold": pin.moderation_hold,
        "can_edit": pin.creator_id == login_session.get("user_id"),
    }

def selected_collection(db, value, user_id):
    if value is None or value == "":
        return None

    if type(value) not in (str, int):
        raise ValueError("Invalid collection")

    try:
        collection_id = int(value)
    except ValueError:
        raise ValueError("Invalid collection")


    collection = db.scalar(
        select(Collection).where(
            Collection.id == collection_id,
            Collection.owner_id == user_id,
        )
    )

    if collection is None:
        raise ValueError("Collection not found")

    return collection.id

def collection_previews(db, collection_id, user_id):
    query = (
        select(Pin, Media)
        .join(Media, Pin.media_id == Media.id)
        .join(CollectionPin, CollectionPin.pin_id == Pin.id)
        .join(Collection, Collection.id == CollectionPin.collection_id)
        .where(
            CollectionPin.collection_id == collection_id,
            (Pin.visibility == "public")
            | ((Collection.owner_id == user_id) & (Pin.creator_id == user_id)),
        )
        .order_by(func.random())
        .limit(4)
    )

    return [
        data["thumbnail"] or data["image"]
        for pin, media in db.execute(query)
        if (data := serialize_pin(pin, media))["image"]
    ]

@app.before_request
def require_api_json():
    if not request.path.startswith("/api/"):
        return

    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return

    if request.endpoint == "create_uploaded_pin":
        request.max_content_length = 11 * 1024 * 1024

        if request.headers.get("Origin") != request.host_url.rstrip("/"):
            return jsonify(error="Invalid request origin"), 403

        if request.mimetype != "multipart/form-data":
            return jsonify(error="Send a file upload"), 415

        return

    if not request.is_json:
        return jsonify(error="Send application/json"), 415

    
@app.get("/")
def index():
    return app.send_static_file("index.html")

@app.get("/api/health")
def health():
    return jsonify(status="ok")

@app.get("/api/pins")
def public_pins():
    search = request.args.get("q", "").strip()
    tag = " ".join(request.args.get("tag", "").split()).casefold()
    if len(tag) > 80:
        return jsonify(error="Tag must be max 80 characters"), 400
    
    if len(search) > 200:
        return jsonify(error="Search must be max 200 characters"), 400
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

    if search:
        terms = func.websearch_to_tsquery("simple", search)

        matching_tag_pins = (
            select(PinTag.pin_id)
            .join(Tag, Tag.id == PinTag.tag_id)
            .where(Tag.search_document.bool_op("@@")(terms))
        )

        query = query.where(
            Pin.search_document.bool_op("@@")(terms)
            | Pin.id.in_(matching_tag_pins)
        )

    if tag:
        tagged_pins = (
            select(PinTag.pin_id)
            .join(Tag, Tag.id == PinTag.tag_id)
            .where(Tag.name == tag)
        )
        query = query.where(Pin.id.in_(tagged_pins))

    if before is not None:
        query = query.where(Pin.id < before)

    with Session() as session:
        rows = session.execute(query).all()
        has_more = len(rows) > 30
        rows = rows[:30]

        pins = [serialize_pin(pin, media) for pin, media in rows]

    return jsonify(pins = pins, next_cursor=pins[-1]["id"] if has_more else None,)

@app.get("/api/pins/<int:pin_id>")
def pin_detail(pin_id):
    if not 0 < pin_id <= 9223372036854775807:
        return jsonify(error="Pin not found"), 404

    query = (
        select(Pin, Media)
        .join(Media, Pin.media_id == Media.id)
        .where(
            Pin.id == pin_id,
            (
                (Pin.visibility == "public")
                | (Pin.creator_id == login_session.get("user_id"))
            ),
        )
    )

    with Session() as session:
        row = session.execute(query).first()

        if row is None:
            return jsonify(error="Pin not found"), 404

        result = serialize_pin(*row)
        result["tags"] = get_tags(session, pin_id)
        return jsonify(result)

@app.post("/api/register")
def register():
    data = request.get_json()

    if not isinstance(data, dict):
        return jsonify(error="Expected JSON object"), 400

    email = data.get("email")
    password = data.get("password")
    name = data.get("display_name")

    if not all(isinstance(value, str) for value in (email, password, name)):
        return jsonify(error="Email, password, display name required"), 400

    email = email.strip().lower()
    name = name.strip()

    if (
        len(email) > 256
        or email.count("@") != 1
        or not all(email.split("@"))
        or any(char.isspace() for char in email)
    ):
        return jsonify(error="Invalid email address"), 400

    if not 1 <= len(name) <= 32:
        return jsonify(error="Display name needs to be 1-32 characters"), 400

    if not 8 <= len(password) <= 64:
        return jsonify(error="Password needs to be 8-64 characters"), 400

    password_hash = generate_password_hash(password)

    try:
        with Session.begin() as db:
            user = User(
                email=email,
                display_name=name,
                password_hash=password_hash,
            )
            db.add(user)
            db.flush()
            user_id = user.id
    except IntegrityError:
        return jsonify(error="Email already used"), 409

    login_session.clear()
    login_session["user_id"] = user_id
    login_session.permanent = True

    return jsonify(user={
        "id": str(user_id),
        "display_name": name,
    }), 201


@app.get("/api/me")
def current_user():
    user_id = login_session.get("user_id")

    if user_id is None:
        return jsonify(user=None)

    with Session() as db:
        user = db.get(User, user_id)

        if user is not None:
            return jsonify(user={
                "id": str(user.id),
                "display_name": user.display_name,
            })

    login_session.clear()
    return jsonify(user=None)

@app.patch("/api/me/profile")
def update_profile():
    user_id = login_session.get("user_id")
    if user_id is None:
        return jsonify(error="Sign in first"), 401

    data = request.get_json()
    name = data.get("display_name") if isinstance(data, dict) else None

    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 32:
        return jsonify(error="Display name must be 1–32 characters"), 400

    with Session.begin() as db:
        user = db.get(User, user_id)
        if user is None:
            return jsonify(error="Sign in first"), 401

        user.display_name = name.strip()
        result = {"id": str(user.id), "display_name": user.display_name}

    return jsonify(user=result)


@app.post("/api/me/password")
def change_password():
    user_id = login_session.get("user_id")
    if user_id is None:
        return jsonify(error="Sign in first"), 401

    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify(error="Expected JSON object"), 400

    current = data.get("current_password")
    new = data.get("new_password")

    if not isinstance(current, str) or not 8 <= len(current) <= 64:
        return jsonify(error="Current password is incorrect"), 400

    if not isinstance(new, str) or not 8 <= len(new) <= 64:
        return jsonify(error="New password must be 8–64 characters"), 400

    with Session.begin() as db:
        user = db.get(User, user_id, with_for_update=True)
        if user is None:
            return jsonify(error="Sign in first"), 401

        if not user.password_hash or not check_password_hash(user.password_hash, current):
            return jsonify(error="Current password is incorrect"), 400

        user.password_hash = generate_password_hash(new)

    return jsonify(ok=True)


@app.post("/api/login")
def login():
    data = request.get_json()

    if not isinstance(data, dict):
        return jsonify(error="Expected JSON object"), 400

    email = data.get("email")
    password = data.get("password")

    if not isinstance(email, str) or not isinstance(password, str):
        return jsonify(error="Email and password required"), 400

    email = email.strip().lower()

    if len(email) > 256 or not 8 <= len(password) <= 64:
        return jsonify(error="Invalid email or password"), 401

    with Session() as db:
        user = db.scalar(select(User).where(User.email == email))
        stored_hash = (
            user.password_hash
            if user is not None and user.password_hash
            else DUMMY_PASSWORD_HASH
        )
        valid = check_password_hash(stored_hash, password)

        if user is None or not user.password_hash or not valid:
            return jsonify(error="Invalid email or password"), 401

        result = {
            "id": str(user.id),
            "display_name": user.display_name,
        }
        user_id = user.id

    login_session.clear()
    login_session["user_id"] = user_id
    login_session.permanent = True

    return jsonify(user=result)

@app.post("/api/logout")
def logout():
    login_session.clear()
    return jsonify(user=None)


@app.get("/api/collections")
def list_collections():
    user_id = login_session.get("user_id")

    if user_id is None:
        return jsonify(error="Sign in first"), 401

    query = (
        select(Collection)
        .where(Collection.owner_id == user_id)
        .order_by(Collection.id.desc())
    )

    with Session() as db:
        collections = [
            {
                "id": str(collection.id),
                "name": collection.name,
                "visibility": collection.visibility,
                "parent_id": (
                    str(collection.parent_id)
                    if collection.parent_id is not None
                    else None
                ),
            }
            for collection in db.scalars(query)
        ]
        for collection in collections:
            collection["previews"] = collection_previews(
                db, int(collection["id"]), user_id
            )

    return jsonify(collections=collections)

@app.post("/api/collections")
def create_collection():
    user_id = login_session.get("user_id")

    if user_id is None:
        return jsonify(error="Sign in first"), 401

    data = request.get_json()

    if not isinstance(data, dict):
        return jsonify(error="Expected JSON object"), 400

    name = data.get("name")

    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200:
        return jsonify(error="Name must be 1-200 characters"), 400

    with Session.begin() as db:
        collection = Collection(
            owner_id=user_id,
            name=name.strip(),
            visibility="private",
        )
        db.add(collection)
        db.flush()

        result = {
            "id": str(collection.id),
            "name": collection.name,
            "visibility": collection.visibility,
            "parent_id": None,
        }

    return jsonify(collection=result), 201

@app.put("/api/collections/<int:collection_id>/pins/<int:pin_id>")
def save_to_collection(collection_id, pin_id):
    user_id = login_session.get("user_id")

    if user_id is None:
        return jsonify(error="Sign in first"), 401

    if not all(0 < value <= 9223372036854775807 for value in (collection_id, pin_id)):
        return jsonify(error="Collection or pin not found"), 404

    with Session.begin() as db:
        collection = db.scalar(
            select(Collection).where(
                Collection.id == collection_id,
                Collection.owner_id == user_id,
            )
        )

        if collection is None:
            return jsonify(error="Collection not found"), 404

        pin = db.scalar(
            select(Pin).where(
                Pin.id == pin_id,
                (
                    (Pin.visibility == "public")
                    | (Pin.creator_id == user_id)
                ),
            )
        )

        if pin is None:
            return jsonify(error="Pin not found"), 404

        db.execute(
            insert(CollectionPin)
            .values(collection_id=collection_id, pin_id=pin_id)
            .on_conflict_do_nothing(
                index_elements=["collection_id", "pin_id"]
            )
        )

    return jsonify(saved=True)

@app.get("/api/collections/<int:collection_id>/pins")
def collection_pins(collection_id):
    user_id = login_session.get("user_id")

    if not 0 < collection_id <= 9223372036854775807:
        return jsonify(error="Collection not found"), 404

    before = request.args.get("before")

    if before is not None:
        try:
            before = int(before)
            if not 0 < before <= 9223372036854775807:
                raise ValueError()
        except ValueError:
            return jsonify(error="Invalid pagination cursor"), 400

    with Session() as db:
        collection = db.scalar(
            select(Collection).where(
                Collection.id == collection_id,
                (Collection.owner_id == user_id)
                | (Collection.visibility == "public"),
            )
        )

        if collection is None:
            return jsonify(error="Collection not found"), 404
        
        pin_visible = Pin.visibility == "public"
        if collection.owner_id == user_id:
            pin_visible = pin_visible | (Pin.creator_id == user_id)

        query = (
            select(Pin, Media)
            .join(Media, Pin.media_id == Media.id)
            .join(CollectionPin, CollectionPin.pin_id == Pin.id)
            .where (
                CollectionPin.collection_id == collection_id,
                pin_visible,
            )
            .order_by(Pin.id.desc())
            .limit(31)
        )

        if before is not None:
            query = query.where(Pin.id < before)

        rows = db.execute(query).all()
        has_more = len(rows) > 30
        pins = [
            serialize_pin(pin, media)
            for pin, media in rows[:30]
        ]

        result = {
            "collection": {
                "id": str(collection.id),
                "name": collection.name,
            },
            "pins": pins,
            "next_cursor": pins[-1]["id"] if has_more else None,
        }

        if before is None:
            visible_collection = (
                (Collection.owner_id == user_id)
                | (Collection.visibility == "public")
            )

            parent = None
            if collection.parent_id is not None:
                parent = db.scalar(
                    select(Collection).where(
                        Collection.id == collection.parent_id,
                        visible_collection,
                    )
                )

            result["parent"] = (
                {"id": str(parent.id), "name": parent.name}
                if parent is not None else None
            )
            result["collection"]["can_manage"] = collection.owner_id == user_id

            children = db.scalars(
                select(Collection)
                .where(Collection.parent_id == collection.id, visible_collection)
                .order_by(Collection.name, Collection.id)
            ).all()

            result["children"] = [
                {
                    "id": str(child.id),
                    "name": child.name,
                    "visibility": child.visibility,
                    "parent_id": str(collection.id),
                    "can_manage": child.owner_id == user_id,
                    "previews": collection_previews(db, child.id, user_id),
                }
                for child in children
            ]

    response = jsonify(result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@app.get("/api/pins/<int:pin_id>/collections")
def pin_collections(pin_id):
    user_id = login_session.get("user_id")

    if user_id is None:
        return jsonify(error="Sign in first"), 401

    if not 0 < pin_id <= 9223372036854775807:
        return jsonify(error="Invalid pin ID"), 400

    query = (
        select(CollectionPin.collection_id)
        .join(Collection, Collection.id == CollectionPin.collection_id)
        .where(
            CollectionPin.pin_id == pin_id,
            Collection.owner_id == user_id,
        )
    )

    with Session() as db:
        collection_ids = [str(value) for value in db.scalars(query)]

    return jsonify(collection_ids=collection_ids)

@app.delete("/api/collections/<int:collection_id>/pins/<int:pin_id>")
def remove_from_collection(collection_id, pin_id):
    user_id = login_session.get("user_id")

    if user_id is None:
        return jsonify(error="Sign in first"), 401

    if not all(0 < value <= 9223372036854775807 for value in (collection_id, pin_id)):
        return jsonify(error="Collection not found"), 404

    with Session.begin() as db:
        collection = db.scalar(
            select(Collection).where(
                Collection.id == collection_id,
                Collection.owner_id == user_id,
            )
        )

        if collection is None:
            return jsonify(error="Collection not found"), 404

        db.execute(
            delete(CollectionPin).where(
                CollectionPin.collection_id == collection_id,
                CollectionPin.pin_id == pin_id,
            )
        )

    return jsonify(saved=False)

@app.patch("/api/collections/<int:collection_id>")
def rename_collection(collection_id):
    user_id = login_session.get("user_id")

    if user_id is None:
        return jsonify(error="Sign in first"), 401

    if not 0 < collection_id <= 9223372036854775807:
        return jsonify(error="Collection not found"), 404

    data = request.get_json()

    if not isinstance(data, dict):
        return jsonify(error="Expected JSON object"), 400

    if "name" not in data and "visibility" not in data:
        return jsonify(error="Provide name or visibility"), 400

    name = data.get("name")
    visibility = data.get("visibility")

    if "name" in data and (not isinstance(name, str) or not 1 <= len(name.strip()) <= 200):
        return jsonify(error="Name must be 1-200 characters"), 400

    if "visibility" in data and visibility not in ("public", "private"):
        return jsonify(error="Invalid visibility"), 400 

    with Session.begin() as db:
        collection = db.scalar(
            select(Collection).where(
                Collection.id == collection_id,
                Collection.owner_id == user_id,
            )
        )

        if collection is None:
            return jsonify(error="Collection not found"), 404

        if name is not None:
            collection.name = name.strip()

        if visibility is not None:
            collection.visibility = visibility

        result = {
            "id": str(collection.id),
            "name": collection.name,
            "visibility": collection.visibility,
        }

    return jsonify(collection=result)

@app.delete("/api/collections/<int:collection_id>")
def delete_collection(collection_id):
    user_id = login_session.get("user_id")

    if user_id is None:
        return jsonify(error="Sign in first"), 401

    if not 0 < collection_id <= 9223372036854775807:
        return jsonify(error="Collection not found"), 404

    with Session.begin() as db:
        collection = db.scalar(
            select(Collection).where(
                Collection.id == collection_id,
                Collection.owner_id == user_id,
            )
        )

        if collection is None:
            return jsonify(error="Collection not found"), 404

        db.delete(collection)

    return jsonify(deleted=True)

@app.post("/api/pins")
def create_pin():
    user_id = login_session.get("user_id")

    if user_id is None:
        return jsonify(error="Sign in first"), 401

    data = request.get_json()

    if not isinstance(data, dict):
        return jsonify(error="Expected JSON object"), 400

    try:
        tags = normalize_tags(data.get("tags", []))
    except ValueError as error:
        return jsonify(error=str(error)), 400

    title = data.get("title")
    image_url = data.get("image_url")
    visibility = data.get("visibility", "private")

    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 300:
        return jsonify(error="Title must be 1-300 characters"), 400

    if not isinstance(image_url, str) or not 1 <= len(image_url) <= 4096:
        return jsonify(error="Enter image URL"), 400

    image_url = image_url.strip()

    try:
        parsed = urlsplit(image_url)
        valid_url = (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not any(char.isspace() for char in image_url)
        )
    except ValueError:
        valid_url = False

    if not valid_url:
        return jsonify(error="Enter a valid image URL"), 400

    if visibility not in ("public", "private"):
        return jsonify(error="Invalid visibility"), 400

    with Session.begin() as db:
        try:
            check_quota(db, user_id)
        except QuotaExceeded as error:
            return jsonify(error=str(error)), 403
        
        try:
            collection_id = selected_collection(
                db, data.get("collection_id"), user_id
            )
        except ValueError as error:
            return jsonify(error=str(error)), 400
        
        media = Media(
            storage_kind="external",
            external_url=image_url,
        )
        db.add(media)
        db.flush()

        pin = Pin(
            creator_id=user_id,
            media_id=media.id,
            title=title.strip(),
            visibility=visibility
        )
        db.add(pin)
        db.flush()

        if collection_id is not None:
            db.add(CollectionPin(
                collection_id=collection_id,
                pin_id=pin.id,
            ))

        replace_tags(db, pin.id, tags)
        result = serialize_pin(pin, media)
        result["tags"] = tags

    return jsonify(pin=result), 201

@app.get("/api/me/pins")
def my_pins():
    user_id = login_session.get("user_id")

    if user_id is None:
        return jsonify(error="Sign in first"), 401

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
        .where(Pin.creator_id == user_id)
        .order_by(Pin.id.desc())
        .limit(31)
    )

    if before is not None:
        query = query.where(Pin.id < before)

    with Session() as db:
        rows = db.execute(query).all()
        has_more = len(rows) > 30
        pins = [
            serialize_pin(pin, media)
            for pin, media in rows[:30]
        ]

    return jsonify(
        pins=pins,
        next_cursor=pins[-1]["id"] if has_more else None,
    )

@app.patch("/api/pins/<int:pin_id>")
def edit_pin(pin_id):
    user_id = login_session.get("user_id")

    if user_id is None:
        return jsonify(error="Sign in first"), 401

    if not 0 < pin_id <= 9223372036854775807:
        return jsonify(error="Pin not found"), 404

    data = request.get_json()

    if not isinstance(data, dict):
        return jsonify(error="Expected JSON object"), 400

    title = data.get("title")
    visibility = data.get("visibility")
    description = data.get("description", "")

    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 300:
        return jsonify(error="Title must be 1-300 characters"), 400

    if visibility not in ("public", "private"):
        return jsonify(error="Invalid visibility"), 400

    if not isinstance(description, str) or len(description) > 10000:
        return jsonify(error="Description must be max 10000 characters"), 400

    try:
        tags = normalize_tags(data["tags"]) if "tags" in data else None
    except ValueError as error:
        return jsonify(error=str(error)), 400

    with Session.begin() as db:
        pin = db.scalar(
            select(Pin).where(
                Pin.id == pin_id,
                Pin.creator_id == user_id,
            )
            .with_for_update()
        )

        if pin is None:
            return jsonify(error="Pin not found"), 404

        if pin.moderation_hold and visibility == "public":
            return jsonify(error="This pin can't be published while under moderation hold"), 403

        pin.title = title.strip()
        pin.visibility = visibility
        pin.description = description.strip()
        if tags is not None:
            replace_tags(db, pin.id, tags)

        result = {
            "id": str(pin.id),
            "title": pin.title,
            "description": pin.description,
            "visibility": pin.visibility,
            "tags": get_tags(db, pin.id),
        }

    return jsonify(pin=result)

@app.delete("/api/pins/<int:pin_id>")
def delete_pin(pin_id):
    user_id = login_session.get("user_id")

    if user_id is None:
        return jsonify(error="Sign in first"), 401

    if not 0 < pin_id <= 9223372036854775807:
        return jsonify(error="Pin not found"), 404

    with Session.begin() as db:
        pin = db.scalar(
            select(Pin).where(
                Pin.id == pin_id,
                Pin.creator_id == user_id,
            )
        )

        if pin is None:
            return jsonify(error="Pin not found"), 404

        db.delete(pin)

    return jsonify(deleted=True)

@app.post("/api/uploads")
def create_uploaded_pin():
    user_id = login_session.get("user_id")

    if user_id is None:
        return jsonify(error="Sign in first"), 401

    title = request.form.get("title", "").strip()
    visibility = request.form.get("visibility", "private")
    file = request.files.get("image")

    if not 1 <= len(title) <= 300:
        return jsonify(error="Title must be 1–300 characters"), 400

    if visibility not in ("public", "private"):
        return jsonify(error="Invalid visibility"), 400

    if file is None:
        return jsonify(error="Choose an image"), 400

    try:
        tags = normalize_tags([
            value.strip()
            for value in request.form.get("tags", "").split(",")
            if value.strip()
        ])
    except ValueError as error:
        return jsonify(error=str(error)), 400

    try:
        prepared = prepare_image(file)
    except ValueError as error:
        return jsonify(error=str(error)), 400

    identifier = uuid4().hex
    image_key = f"images/{identifier}.webp"
    thumbnail_key = f"thumbnails/{identifier}.webp"
    keys = [image_key, thumbnail_key]

    try:
        with Session.begin() as db:
            try:
                check_quota(db, user_id, len(prepared["image"]))
            except QuotaExceeded as error:
                return jsonify(error=str(error)), 403
            
            try:
                collection_id = selected_collection(
                    db, request.form.get("collection_id"), user_id
                )
            except ValueError as error:
                return jsonify(error=str(error)), 400

            put_image(image_key, prepared["image"])
            put_image(thumbnail_key, prepared["thumbnail"])

            media = Media(
                storage_kind="hosted",
                object_key=image_key,
                thumbnail_key=thumbnail_key,
                mime_type=prepared["mime_type"],
                width=prepared["width"],
                height=prepared["height"],
                byte_size=len(prepared["image"]),
            )
            db.add(media)
            db.flush()

            pin = Pin(
                creator_id=user_id,
                media_id=media.id,
                title=title,
                visibility=visibility,
            )
            db.add(pin)
            db.flush()

            if collection_id is not None:
                db.add(CollectionPin(
                    collection_id=collection_id,
                    pin_id=pin.id,
                ))

            replace_tags(db, pin.id, tags)
            result = serialize_pin(pin, media)
            result["tags"] = tags

    except Exception:
        try:
            delete_images(keys)
        except Exception:
            app.logger.exception("Can't clean up failed upload")
        raise

    return jsonify(pin=result), 201

@app.cli.command("cleanup-media")
@click.option("--apply", is_flag=True, help="Nuke unused media")
def cleanup_media(apply):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    unused = ~select(Pin.id).where(Pin.media_id == Media.id).exists()

    with Session() as db:
        candidates = list(db.scalars(
            select(Media.id)
            .where(Media.created_at < cutoff, unused)
            .order_by(Media.id)
            .limit(100)
        ))

    if not apply:
        click.echo(f"Found {len(candidates)} unused media records. Nothing deleted")
        return

    removed = 0

    for media_id in candidates:
        with Session.begin() as db:
            media = db.scalar(
                select(Media)
                .where(Media.id == media_id)
                .with_for_update(skip_locked=True)
            )

            if media is None:
                continue

            if media.storage_kind == "hosted":
                delete_images([
                    key
                    for key in (media.object_key, media.thumbnail_key)
                    if key
                ])

            db.delete(media)

        removed += 1

    click.echo(f"Removed {removed} unused media records")

@app.before_request
def limit_requests():
    rules = {
        "login": ("ip", 10, 60),
        "register": ("ip", 3, 3600),
        "create_uploaded_pin": ("account", 6, 60),
        "create_pin": ("account", 20, 60),
        "preview_pinterest_board": ("account", 4, 60),
        "import_pinterest_section": ("account", 4, 60),
        "change_password": ("account", 5, 60),
        "report_pin": ("account", 10, 3600),
    }

    rule = rules.get(request.endpoint)

    if rule is None or request.method != "POST":
        return

    kind, limit, seconds = rule

    identity = (
        request.remote_addr
        if kind == "ip"
        else login_session.get("user_id")
    )

    if identity is None:
        return

    retry_after = check_limit(
        request.endpoint,
        str(identity),
        limit,
        seconds,
        app.config["SECRET_KEY"],
    )

    if retry_after:
        return(
            jsonify(error=f"Too many requests. Try again in {retry_after} seconds"), 
            429,
            {"Retry-After": str(retry_after)},
        )

@app.cli.command("cleanup-request-limits")
def cleanup_request_limits():
    import time
    cutoff = int(time.time()) - 86400

    with Session.begin() as db:
        db.execute(
            delete(RequestLimit).where(RequestLimit.window < cutoff)
        )

    click.echo("Removed old request limit counters")

@app.get("/api/me/usage")
def my_usage():
    user_id = login_session.get("user_id")

    if user_id is None:
        return jsonify(error="Sign in first"), 401

    with Session() as db:
        return jsonify(account_usage(db, user_id))


@app.get("/api/pins/<int:pin_id>/related")
def related_pins(pin_id):
    if not 0 < pin_id <= 9223372036854775807:
        return jsonify(error="Pin not found"), 404

    before = request.args.get("before")

    if before is not None:
        try:
            score, last_id = map(int, before.split(":"))
            if not (1 <= score <= 20 and 0 < last_id <= 9223372036854775807):
                raise ValueError
        except ValueError:
            return jsonify(error="Invalid pagination cursor"), 400

    source_tags = select(PinTag.tag_id).where(PinTag.pin_id == pin_id)

    matches = (
        select(PinTag.pin_id, func.count().label("score"))
        .where(
            PinTag.tag_id.in_(source_tags),
            PinTag.pin_id != pin_id,
        )
        .group_by(PinTag.pin_id)
        .subquery()
    )

    query = (
        select(Pin, Media, matches.c.score)
        .join(matches, matches.c.pin_id == Pin.id)
        .join(Media, Media.id == Pin.media_id)
        .where(Pin.visibility == "public")
        .order_by(matches.c.score.desc(), Pin.id.desc())
        .limit(13)
    )

    if before is not None:
        query = query.where(
            (matches.c.score < score)
            | ((matches.c.score == score) & (Pin.id < last_id))
        )

    with Session() as db:
        source = db.scalar(
            select(Pin.id).where(
                Pin.id == pin_id,
                (Pin.visibility == "public")
                | (Pin.creator_id == login_session.get("user_id")),
            )
        )

        if source is None:
            return jsonify(error="Pin not found"), 404

        rows = db.execute(query).all()
        page = rows[:12]
        pins = [serialize_pin(pin, media) for pin, media, _ in page]

        next_cursor = None
        if len(rows) > 12:
            last_pin, _, last_score = page[-1]
            next_cursor = f"{last_score}:{last_pin.id}"

    return jsonify(pins=pins, next_cursor=next_cursor)

@app.post("/api/import/pinterest/preview")
def preview_pinterest_board():
    if login_session.get("user_id") is None:
        return jsonify(error="Sign in first"), 401

    data = request.get_json()

    if not isinstance(data, dict):
        return jsonify(error="Expected a JSON object"), 400

    try:
        return jsonify(preview_board(data.get("url")))
    except BoardURLError as error:
        return jsonify(error=str(error)), 400
    except BoardPreviewError as error:
        return jsonify(error=str(error)), 502



@app.post("/api/import/pinterest/page")
@app.post("/api/import/pinterest/section")
def import_pinterest_section():
    user_id = login_session.get("user_id")
    if user_id is None:
        return jsonify(error="Sign in first"), 401

    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify(error="Expected JSON object"), 400

    pin_visibility = data.get("pin_visibility", "private")

    if pin_visibility not in ("public", "private"):
        return jsonify(error="Invalid pin visibility"), 400

    use_section_tags = data.get("use_section_tags", False)

    if not isinstance(use_section_tags, bool):
        return jsonify(error="use_section_tags must be true or false"), 400

    url = data.get("url")
    section_id = data.get("section_id")
    cursor = data.get("cursor")

    if section_id is not None and not isinstance(section_id, str):
        return jsonify(error="Invalid board section"), 400

    if cursor is not None and (
        not isinstance(cursor, str) or not 1 <= len(cursor) <= 8192
    ):
        return jsonify(error="Invalid import cursor"), 400

    try:
        board = preview_board(url)
        _, _, source = board_path(url)

        section = None
        section_tag = ""

        if section_id is not None:
            section = next(
                (item for item in board["sections"] if item["id"] == section_id),
                None,
            )
            if section is None:
                return jsonify(error="Section not found in the board preview."), 400

            section_tag = " ".join(
                str(section["name"]).replace(",", " ").split()
            ).casefold()[:80].strip()

        page = board_pin_page(
            source, board["id"], section_id=section_id, cursor=cursor
        )
    except BoardURLError as error:
        return jsonify(error=str(error)), 400
    except BoardPreviewError as error:
        return jsonify(error=str(error)), 502

    if not page["pins"]:
        return jsonify(
            added=0, reused=0, linked=0, skipped_in_sections=0,
            next_cursor=page["next_cursor"],
            quota_reached=False,
        )

    added = reused = linked = skipped_in_sections = 0
    quota_reached = False

    with Session.begin() as db:
        account_id = db.scalar(
            select(User.id).where(User.id == user_id).with_for_update()
        )
        if account_id is None:
            return jsonify(error="Account not found"), 401

        remaining = max(0, PIN_LIMIT - account_usage(db, user_id)["pins"])

        def get_collection(key, name, parent_id=None):
            collection = db.scalar(
                select(Collection).where(
                    Collection.owner_id == user_id,
                    Collection.import_key == key,
                )
            )
            if collection is None:
                collection = Collection(
                    owner_id=user_id,
                    parent_id=parent_id,
                    name=str(name)[:200],
                    visibility="private",
                    import_key=key,
                )
                db.add(collection)
                db.flush()
            return collection

        board_key = f"pinterest:board:{board['id']}"
        parent = get_collection(board_key, board["name"])
        target = parent

        if section is not None:
            target = get_collection(
                f"{board_key}:section:{section_id}",
                section["name"],
                parent.id,
            )

        for item in page["pins"]:
            asset = urlsplit(item["image_url"]).path.split("/", 2)[-1]
            digest = sha256(asset.encode()).hexdigest()
            pin_key = f"{board_key}:image:{digest}"

            pin = db.scalar(
                select(Pin).where(
                    Pin.creator_id == user_id,
                    Pin.import_key == pin_key,
                )
            )

            if section is None and pin is not None:
                in_section = db.scalar(
                    select(CollectionPin.pin_id)
                    .join(Collection, Collection.id == CollectionPin.collection_id)
                    .where(
                        Collection.parent_id == parent.id,
                        CollectionPin.pin_id == pin.id,
                    )
                    .limit(1)
                )

                if in_section is not None:
                    skipped_in_sections += 1
                    continue

            if pin is None:
                if remaining == 0:
                    quota_reached = True
                    break

                media = Media(
                    storage_kind="external",
                    external_url=item["image_url"],
                )
                db.add(media)
                db.flush()

                pin = Pin(
                    creator_id=user_id,
                    media_id=media.id,
                    title=item["title"],
                    description=item["description"],
                    source_url=item["source_url"],
                    visibility=pin_visibility,
                    import_key=pin_key,
                )
                db.add(pin)
                db.flush()

                if use_section_tags and section_tag:
                    replace_tags(db, pin.id, [section_tag])

                added += 1
                remaining -= 1
            else:
                reused += 1

            membership = db.scalar(
                insert(CollectionPin)
                .values(collection_id=target.id, pin_id=pin.id)
                .on_conflict_do_nothing(
                    index_elements=["collection_id", "pin_id"]
                )
                .returning(CollectionPin.pin_id)
            )
            if membership is not None:
                linked += 1

        result = {
            "collection_id": str(target.id),
            "added": added,
            "reused": reused,
            "linked": linked,
            "next_cursor": cursor if quota_reached else page["next_cursor"],
            "quota_reached": quota_reached,
            "skipped_in_sections": skipped_in_sections
        }

    return jsonify(result)


REPORT_REASONS = {
    "ai_generated", "spam", "harassment",
    "sexual_content", "copyright", "other",
}


@app.post("/api/pins/<int:pin_id>/report")
def report_pin(pin_id):
    user_id = login_session.get("user_id")
    if user_id is None:
        return jsonify(error="Sign in to report a pin."), 401

    if not 0 < pin_id <= 9223372036854775807:
        return jsonify(error="Pin not found."), 404

    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify(error="Expected a JSON object."), 400

    reason = data.get("reason")
    note = data.get("note", "")

    if not isinstance(reason, str) or reason not in REPORT_REASONS:
        return jsonify(error="Choose a report reason."), 400

    if not isinstance(note, str) or len(note) > 1000:
        return jsonify(error="Notes must be at most 1,000 characters."), 400

    with Session.begin() as db:
        public_pin = db.scalar(
            select(Pin.id).where(Pin.id == pin_id, Pin.visibility == "public")
        )
        if public_pin is None:
            return jsonify(error="Pin not found."), 404

        created = db.scalar(
            insert(PinReport)
            .values(
                pin_id=pin_id,
                reporter_id=user_id,
                reason=reason,
                note=note.strip(),
            )
            .on_conflict_do_nothing(index_elements=["pin_id", "reporter_id"])
            .returning(PinReport.pin_id)
        )

    return jsonify(reported=True, already_reported=created is None)


@app.cli.command("pin-reports")
@click.option("--limit", type=click.IntRange(1, 200), default=50)
def list_pin_reports(limit):
    query = (
        select(PinReport)
        .where(PinReport.status == "pending")
        .order_by(PinReport.created_at, PinReport.pin_id, PinReport.reporter_id)
        .limit(limit)
    )

    with Session() as db:
        reports = db.scalars(query).all()

        if not reports:
            click.echo("No pending reports.")
            return

        for report in reports:
            click.echo(json.dumps({
                "pin_id": str(report.pin_id),
                "reason": report.reason,
                "note": report.note,
                "created_at": report.created_at.isoformat(),
            }))


@app.cli.command("resolve-pin-reports")
@click.argument("pin_id", type=click.IntRange(1, 9223372036854775807))
@click.option("--action", type=click.Choice(["dismiss", "unpublish"]), required=True)
def resolve_pin_reports(pin_id, action):
    with Session.begin() as db:
        pin = db.get(Pin, pin_id, with_for_update=True)

        if pin is None:
            raise click.ClickException("Pin not found")

        resolved = db.execute(
            update(PinReport)
            .where(PinReport.pin_id == pin_id, PinReport.status == "pending")
            .values(status="dismissed" if action == "dismiss" else "actioned")
        ).rowcount

        if not resolved:
            click.echo("No pending reports for this pin")
            return

        if action == "unpublish":
            pin.visibility = "private"
            pin.moderation_hold = True

    click.echo(f"Resolved {resolved} report(s) for pin {pin_id}: {action}")


@app.cli.command("clear-pin-hold")
@click.argument("pin_id", type=click.IntRange(1, 9223372036854775807))
def clear_pin_hold(pin_id):
    with Session.begin() as db:
        pin = db.get(Pin, pin_id, with_for_update=True)
        if pin is None:
            raise click.ClickException("Pin not found")

        if not pin.moderation_hold:
            click.echo("This pin is not under moderation hold")
            return

        pin.moderation_hold = False

    click.echo(f"Cleared moderation hold on pin {pin_id}. The pin is still private.")