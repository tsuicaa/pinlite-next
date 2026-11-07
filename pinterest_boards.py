import json
import re
import time
from urllib.parse import urlencode, urlsplit, quote, unquote
from urllib.request import HTTPRedirectHandler, Request, build_opener
from images import prepare_image


BASE = "https://www.pinterest.com"


class BoardURLError(ValueError):
    pass


class BoardPreviewError(Exception):
    pass

class BoardImageError(Exception):
    pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def prepare_board_image(image_url):
    try:
        parsed = urlsplit(image_url)

        if parsed.scheme != "https" or parsed.netloc.lower() != "i.pinimg.com":
            raise ValueError("Invalid Pinterest image host")

        request = Request(image_url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "image/*",
        })

        with build_opener(NoRedirect).open(request, timeout=6) as response:
            return prepare_image(response)

    except (OSError, ValueError) as error:
        raise BoardImageError("Can't read the Pinterest image") from error


def board_path(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise BoardURLError("Enter a Pinterest board URL")

    value = value.strip()

    try:
        url = urlsplit(value if "://" in value else f"https://{value}")
        valid = (
            url.scheme == "https"
            and re.fullmatch(
                r"(?:www\.|[a-z]{2}(?:-[a-z]{2})?\.)?pinterest\.com",
                url.netloc.lower(),
            ) is not None
        )
    except ValueError:
        valid = False

    match = re.fullmatch(
        r"/([A-Za-z0-9_-]+)/([^/]+)/?", url.path
    ) if valid else None

    if match is None:
        raise BoardURLError("Use the full Pinterest board URL (/username/board/)")

    username, encoded_slug = match.groups()
    try:
        slug = unquote(encoded_slug, errors="strict")
    except UnicodeDecodeError:
        raise BoardURLError("Invalid encoding in Pinterest board URL") from None

    if slug in (".", "..") or "/" in slug or "\\" in slug or not slug.isprintable():
        raise BoardURLError("Invalid Pinterest board name")

    return username, slug, f"/{username}/{quote(slug, safe='')}/"


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

        payload = json.loads(body)
        envelope = payload["resource_response"]
        data = envelope["data"]

        if data is None or envelope.get("error") or envelope.get("status") == "failure":
            raise BoardPreviewError("Pinterest did not return public board data.")

        bookmark = envelope.get("bookmark")
        if not bookmark:
            bookmarks = (
                (payload.get("resource") or {})
                .get("options", {})
                .get("bookmarks")
            )
            if isinstance(bookmarks, list) and bookmarks:
                bookmark = bookmarks[0]

        return data, bookmark
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
        "id": board_id,
        "url": BASE + source,
        "reported_pin_count": board.get("pin_count"),
        "first_page_pin_count": sum(
            row.get("type") == "pin" or bool(row.get("id") and row.get("images"))
            for row in rows(feed)
        ),
        "has_more_pins": bool(bookmark and bookmark != "-end-"),
        "sections": [
            {
                "id": str(row["id"]),
                "name": row.get("title") or "Untitled section",
                "pin_count": row.get("pin_count"),
            }
            for row in rows(sections)
            if re.fullmatch(r"[0-9]{1,30}", str(row.get("id", "")))
        ],
        "has_more_sections": bool(section_bookmark and section_bookmark != "-end-"),
    }

def board_pin_page(source, board_id, *, section_id=None, cursor=None, filter_section_pins=False):
    options = {"field_set_key": "react_grid_pin", "page_size": 25}

    if section_id is None:
        name = "BoardFeedResource"
        options.update(
            board_id=board_id,
            filter_section_pins=filter_section_pins,
            prepend=False,
        )
    else:
        name = "BoardSectionPinsResource"
        options["section_id"] = section_id

    if cursor:
        options["bookmarks"] = [cursor]

    data, bookmark = resource(name, source, options)
    feed = rows(data)
    if cursor and not feed and bookmark in (None, "", "-end-", cursor):
        data, bookmark = resource(name, source, options)
        feed = rows(data)
    pins = []

    for row in feed:
        images = row.get("images")
        if not isinstance(images, dict):
            continue

        image_url = None

        for size in ("orig", "736x", "564x", "474x", "236x"):
            image = images.get(size)
            url = image.get("url") if isinstance(image, dict) else None

            if not isinstance(url, str):
                continue

            try:
                parsed = urlsplit(url)
            except ValueError:
                continue

            if (
                parsed.scheme == "https"
                and parsed.netloc.lower() == "i.pinimg.com"
                and parsed.path not in ("", "/")
            ):
                image_url = url
                break

        if image_url is None:
            continue

        pin_id = str(row.get("id", ""))
        source_url = None
        link = row.get("link")

        if isinstance(link, str):
            link = link.strip()
            try:
                parsed = urlsplit(link)
                if (
                    len(link) <= 4096
                    and parsed.scheme in ("http", "https")
                    and parsed.hostname
                    and parsed.username is None
                    and parsed.password is None
                ):
                    source_url = link
            except ValueError:
                pass

        description = row.get("description")
        if not isinstance(description, str):
            description = ""

        pins.append({
            "pinterest_id": pin_id,
            "title": str(row.get("title") or row.get("grid_title") or "Untitled pin")[:300],
            "description": description.replace("\x00", "").strip()[:10000],
            "image_url": image_url,
            "source_url": source_url,
        })

    if not feed or not isinstance(bookmark, str) or bookmark in ("", "-end-", cursor):
        bookmark = None

    return {"pins": pins, "next_cursor": bookmark}