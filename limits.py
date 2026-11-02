import hashlib
import hmac 
import time

from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert

from db import Session
from models import RequestLimit

def check_limit(scope, identity, limit, seconds, secret):
    now = int(time.time())
    window = now // seconds * seconds

    key = hmac.new(
        secret.encode(),
        f"{scope}:{identity}".encode(),
        hashlib.sha256,
    ).hexdigest()

    statement = insert(RequestLimit).values(
        key=key,
        window=window,
        count=1,
    )

    statement= statement.on_conflict_do_update(
        index_elements=["key"],
        set_={
            "window": window,
            "count": case(
                (RequestLimit.window == window, RequestLimit.count + 1),
                else_=1,
            ),
        },
    ).returning(RequestLimit.count)

    with Session.begin() as db:
        count = db.scalar(statement)

    return window + seconds - now if count > limit else 0