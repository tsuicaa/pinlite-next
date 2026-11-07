from flask import Blueprint, abort, render_template, session
from sqlalchemy import func, select

from db import Session
from models import Pin, PinReport, User

admin = Blueprint("admin", __name__, url_prefix="/admin")


@admin.before_request
def require_admin():
    user_id = session.get("user_id")
    if user_id is None:
        abort(403)

    with Session() as db:
        allowed = db.scalar(select(User.is_admin).where(User.id == user_id))

    if not allowed:
        abort(403)


@admin.get("")
def overview():
    with Session() as db:
        users = db.scalar(select(func.count()).select_from(User))
        pins = dict(db.execute(
            select(Pin.visibility, func.count()).group_by(Pin.visibility)
        ).all())
        pending_reports = db.scalar(
            select(func.count()).select_from(PinReport)
            .where(PinReport.status == "pending")
        )

    return render_template(
        "admin.html", users=users, pins=pins, pending_reports=pending_reports
    ), 200, {"Cache-Control": "no-store"}