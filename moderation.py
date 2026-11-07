from sqlalchemy import update

from db import Session
from models import Pin, PinReport


def resolve_reports(pin_id, action):
    if action not in ("dismiss", "unpublish"):
        raise ValueError("Invalid moderation action")

    with Session.begin() as db:
        pin = db.get(Pin, pin_id, with_for_update=True)
        if pin is None:
            return None

        resolved = db.execute(
            update(PinReport)
            .where(PinReport.pin_id == pin_id, PinReport.status == "pending")
            .values(status="dismissed" if action == "dismiss" else "actioned")
        ).rowcount

        if resolved and action == "unpublish":
            pin.visibility = "private"
            pin.moderation_hold = True

        return resolved