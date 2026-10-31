import os
from urllib.parse import quote
from datetime import timedelta

from flask import Flask, jsonify, request, session as login_session
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert
from werkzeug.security import generate_password_hash, check_password_hash

from db import Session
from models import Collection, CollectionPin, Media, Pin, User

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
    base = os.environ.get("MEDIA_BASE_URL", "").rstrip("/")
    if not key or not base:
        return None
    return f"{base}/{quote(key, safe='/')}"

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
    }


@app.before_request
def require_api_json():
    if (
        request.path.startswith("/api/")
        and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and not request.is_json
    ):
        return jsonify(error="Send application/json"), 415

@app.get("/")
def index():
    return app.send_static_file("index.html")

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

        pins = [serialize_pin(pin, media) for pin, media in rows]

    return jsonify(pins = pins, next_cursor=pins[-1]["id"] if has_more else None,)

@app.get("/api/pins/<int:pin_id>")
def pin_detail(pin_id):
    if not 0 < pin_id <= 9223372036854775807:
        return jsonify(error="Pin not found"), 404

    query = (
        select(Pin, Media)
        .join(Media, Pin.media_id == Media.id)
        .where(Pin.id == pin_id, Pin.visibility == "public")
    )

    with Session() as session:
        row = session.execute(query).first()

        if row is None:
            return jsonify(error="Pin not found"), 404

        return jsonify(serialize_pin(*row))

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

    if user_id is None:
        return jsonify(error="Sign in first"), 401

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
                Collection.owner_id == user_id,
            )
        )

        if collection is None:
            return jsonify(error="Collection not found"), 404

        query = (
            select(Pin, Media)
            .join(Media, Pin.media_id == Media.id)
            .join(CollectionPin, CollectionPin.pin_id == Pin.id)
            .where (
                CollectionPin.collection_id == collection_id,
                (
                    (Pin.visibility == "public")
                    | (Pin.creator_id == user_id)
                ),
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

    return jsonify(result)

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