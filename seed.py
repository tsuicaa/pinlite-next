from sqlalchemy import select

from db import Session
from models import Media, Pin, User


with Session.begin() as session:
    email = "demo@pinlite.invalid"

    if session.scalar(select(User.id).where(User.email == email)):
        raise SystemExit("Demo dat already exists")

    user = User(email=email, display_name="Demo")
    session.add(user)
    session.flush()

    media = Media(
        storage_kind="external",
        external_url="https://placehold.co/600x800/png",
        mime_type="image/png",
        width=600,
        height=800,
    )
    session.add(media)
    session.flush()

    for number in range(1, 37):
        session.add(Pin(
            creator_id=user.id,
            media_id=media.id,
            title=f"Demo pin {number}",
            description="Dev demo",
            visibility="private" if number == 36 else "public",
        ))