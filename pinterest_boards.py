import json
import re
import time
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


BASE = "https://www.pinterest.com"


class BoardURLError(ValueError):
    pass


class BoardPreviewError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def board_path(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise BoardURLError("Enter a Pinterest board URL")

    value = value.strip()

    try:
        url = urlsplit(value if "://" in value else f"https://{value}")
        valid = (
            url.scheme == "https"
            and url.netloc.lower() in ("pinterest.com", "www.pinterest.com")
        )
    except ValueError:
        valid = False

    match = re.fullmatch(
        r"/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)/?", url.path
    ) if valid else None

    if match is None:
        raise BoardURLError("Use the full Pinterest board URL: /username/board/.")

    username, slug = match.groups()
    return username, slug, f"/{username}/{slug}/"


def resource(name, source, options):
    params = urlencode({
        "source_url": source,
        "data": json.dumps({"options": options, "context": {}}),
        "_": int(time.time() * 1000),
    })

    request = Request(f"{BASE}/resource/{name}/get/?{params}", headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Referer": BASE + source,
        "X-Requested-With": "XMLHttpRequest",
        "X-Pinterest-AppState": "active",
        "X-Pinterest-PWS-Handler": "www/ideas.js",
        "X-Pinterest-Source-Url": source,
    })

    try:
        with build_opener(NoRedirect).open(request, timeout=6) as response:
            body = response.read(5_000_001)

        if len(body) > 5_000_000:
            raise BoardPreviewError("Pinterest's response was too large")

        envelope = json.loads(body)["resource_response"]
        data = envelope["data"]

        if data is None or envelope.get("error") or envelope.get("status") == "failure":
            raise BoardPreviewError("Pinterest did not return public board data.")

        return data, envelope.get("bookmark")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise BoardPreviewError("Could not read the board from Pinterest") from error


def rows(data):
    if isinstance(data, dict):
        data = data.get("results", data.get("data"))

    if not isinstance(data, list):
        raise BoardPreviewError("Pinterest changed its board response format")

    return [row for row in data if isinstance(row, dict)]


def preview_board(value):
    username, slug, source = board_path(value)

    board, _ = resource("BoardResource", source, {
        "username": username,
        "slug": slug,
        "field_set_key": "detailed",
    })

    if (
        not isinstance(board, dict)
        or not re.fullmatch(r"[0-9]{1,30}", str(board.get("id", "")))
        or board.get("is_secret")
        or board.get("privacy") in ("secret", "private")
    ):
        raise BoardPreviewError("No public board found")

    board_id = str(board["id"])

    feed, bookmark = resource("BoardFeedResource", source, {
        "board_id": board_id,
        "field_set_key": "react_grid_pin",
        "filter_section_pins": False,
        "prepend": False,
        "page_size": 25,
    })

    sections, section_bookmark = resource("BoardSectionsResource", source, {
        "board_id": board_id,
        "page_size": 25,
    })

    return {
        "name": board.get("name") or slug,
        "url": BASE + source,
        "reported_pin_count": board.get("pin_count"),
        "first_page_pin_count": sum(
            row.get("type") == "pin" or bool(row.get("id") and row.get("images"))
            for row in rows(feed)
        ),
        "has_more_pins": bool(bookmark and bookmark != "-end-"),
        "sections": [
            {"id": str(row["id"]), "name": row.get("title") or "Untitled section"}
            for row in rows(sections)
            if re.fullmatch(r"[0-9]{1,30}", str(row.get("id", "")))
        ],
        "has_more_sections": bool(section_bookmark and section_bookmark != "-end-"),
    }