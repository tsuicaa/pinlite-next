from flask import Blueprint, abort, render_template, session, request, current_app, redirect, url_for
from sqlalchemy import func, select

from db import Session
from models import Pin, PinReport, User, Media
from storage import image_url
from secrets import compare_digest, token_urlsafe

from moderation import resolve_reports
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

admin = Blueprint("admin", __name__, url_prefix="/admin")

def read_server_health():
    try:
        health = json.loads(
            Path("/var/lib/pinlite-health/status.json").read_text(encoding="utf-8")
        )
        collected_at = datetime.fromisoformat(health["collected_at"])
        health["stale"] = datetime.now(timezone.utc) - collected_at > timedelta(minutes=3)
        return health
    except (OSError, ValueError, KeyError, TypeError):
        return None

def admin_csrf_token():
    if "admin_csrf" not in session:
        session["admin_csrf"] = token_urlsafe(32)
    return session["admin_csrf"]


def require_admin_csrf():
    expected = session.get("admin_csrf")
    supplied = request.form.get("csrf_token", "")
    if not expected or not compare_digest(expected.encode(), supplied.encode()):
        abort(403)

@admin.before_request
def require_admin():
    user_id = session.get("user_id")
    if user_id is None:
        abort(403)

    with Session() as db:
        allowed = db.scalar(select(User.is_admin).where(User.id == user_id, User.is_suspended.is_(False)))

    if not allowed:
        abort(403)


@admin.get("")
def overview():
    before = request.args.get("before")

    if before is not None:
        try:
            before = int(before)
            if not 0 < before <= 9223372036854775807:
                raise ValueError
        except ValueError:
            abort(400)

    user_query = (
        select(User.id, User.email, User.display_name, User.is_admin, User.is_suspended)
        .order_by(User.id.desc())
        .limit(26)
    )
    if before is not None:
        user_query = user_query.where(User.id < before)

    with Session() as db:
        users = db.scalar(select(func.count()).select_from(User))
        pins = dict(db.execute(
            select(Pin.visibility, func.count()).group_by(Pin.visibility)
        ).all())
        pending_reports = db.scalar(
            select(func.count()).select_from(PinReport)
            .where(PinReport.status == "pending")
        )
        rows = db.execute(user_query).all()
        accounts = rows[:25]
        next_before = accounts[-1].id if len(rows) > 25 else None
        account_ids = [account.id for account in accounts]

        pin_counts = dict(db.execute(
            select(Pin.creator_id, func.count())
            .where(Pin.creator_id.in_(account_ids))
            .group_by(Pin.creator_id)
        ).all())

        owned_media = (
            select(Pin.creator_id, Pin.media_id)
            .where(Pin.creator_id.in_(account_ids))
            .distinct()
            .subquery()
        )

        storage_bytes = dict(db.execute(
            select(owned_media.c.creator_id, func.sum(Media.byte_size))
            .join(Media, Media.id == owned_media.c.media_id)
            .where(Media.storage_kind == "hosted")
            .group_by(owned_media.c.creator_id)
        ).all())

    return render_template(
        "admin.html", 
        users=users, 
        pins=pins, 
        pending_reports=pending_reports,
        accounts=accounts,
        pin_counts=pin_counts,
        storage_bytes=storage_bytes,
        next_before=next_before,
        before=before,
        csrf_token=admin_csrf_token(),
        health=read_server_health(),
    ), 200, {"Cache-Control": "no-store"}

@admin.get("/reports")
def reports():
    with Session() as db:
        rows = db.execute(
            select(
                Pin.id.label("pin_id"),
                Pin.title,
                Pin.visibility,
                Media.thumbnail_key,
                PinReport.reason,
                PinReport.note,
                PinReport.created_at,
            )
            .join(PinReport, PinReport.pin_id == Pin.id)
            .join(Media, Media.id == Pin.media_id)
            .where(PinReport.status == "pending")
            .order_by(PinReport.created_at, PinReport.pin_id, PinReport.reporter_id)
            .limit(51)
        ).all()

    csrf_token=admin_csrf_token()

    grouped_reports = {}
    for row in rows[:50]:
        grouped_reports.setdefault(row.pin_id, []).append(row)

    return render_template(
        "admin-reports.html",
        report_groups=grouped_reports.values(),
        csrf_token=admin_csrf_token(),
        has_more=len(rows) > 50,
        image_url=image_url,
    ), 200, {"Cache-Control": "no-store"}

@admin.post("/reports/<int:pin_id>/resolve")
def resolve_report_group(pin_id):
    require_admin_csrf()

    action = request.form.get("action")
    if action not in ("dismiss", "unpublish"):
        abort(400)
    if not 0 < pin_id <= 9223372036854775807:
        abort(404)

    resolved = resolve_reports(pin_id, action)
    if resolved is None:
        abort(404)

    if resolved:
        current_app.logger.warning(
            "Moderation: admin=%s pin=%s action=%s reports=%s",
            session["user_id"], pin_id, action, resolved,
        )

    return redirect(url_for("admin.reports"), code=303)


@admin.post("/users/<int:user_id>/status")
def set_user_status(user_id):
    require_admin_csrf()
    action = request.form.get("action")
    if action not in ("suspend", "restore"):
        abort(400)
    if not 0 < user_id <= 9223372036854775807:
        abort(404)

    suspended = action == "suspend"
    with Session.begin() as db:
        account = db.get(User, user_id, with_for_update=True)
        if account is None:
            abort(404)
        if account.is_admin:
            abort(403)

        changed = account.is_suspended != suspended
        account.is_suspended = suspended

    if changed:
        current_app.logger.warning(
            "Account status: admin=%s user=%s action=%s",
            session["user_id"], user_id, action,
        )

    return redirect(url_for("admin.overview"), code=303)