import os

from sqlalchemy import func, select
from models import Media, Pin, User

PIN_LIMIT = int(os.environ.get("PIN_LIMIT", "1000"))
UPLOAD_LIMIT = int(os.environ.get("UPLOAD_LIMIT_BYTES", str(250 * 1024 * 1024)))

class QuotaExceeded(ValueError):
    pass

def check_quota(db, user_id, upload_bytes=0):
    user = db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
    )

    if user is None:
        raise QuotaExceeded("Account not found")

    pin_count = db.scalar(
        select(func.count())
        .select_from(Pin)
        .where(Pin.creator_id == user_id)
    )

    if pin_count >= PIN_LIMIT:
        raise QuotaExceeded(f"Account limit reached: {PIN_LIMIT} pins")

    if upload_bytes:
        media_ids = select(Pin.media_id).where(
            Pin.creator_id == user_id
        )

    if upload_bytes:
        media_ids = select(Pin.media_id).where(
            Pin.creator_id == user_id
        )

        used = db.scalar(
            select(func.coalesce(func.sum(Media.byte_size), 0))
            .where(
                Media.storage_kind == "hosted",
                Media.id.in_(media_ids),
            )
        )

        if use + upload_bytes > UPLOAD_LIMIT:
            raise QuotaExceeded("Your image storage quota is full")