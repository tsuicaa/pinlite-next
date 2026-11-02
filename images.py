from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 20_000_000


def prepare_image(file):
    data = file.read(MAX_BYTES + 1)

    if not data or len(data) > MAX_BYTES:
        raise ValueError("Image must be between 1 byte and 10 MB")

    try:
        with Image.open(BytesIO(data)) as original:
            if original.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Allowed formats are JPEG, PNG or WebP")

            if original.width * original.height > MAX_BYTES:
                raise ValueError("Image must be max 20 megapixels")

            if getattr(original, "is_animated", False):
                raise ValueError("Animated images aren't supported yet")

            original.load()

            keep_original = (
                original.format == "WEBP"
                and not any(
                    original.info.get(key)
                    for key in ("exif", "icc_profile", "xmp")
                )
            )

            image = ImageOps.exif_transpose(original).convert("RGBA")

    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("Cannot read image") from None

    if keep_original:
        full_image = data
    else:
        full = BytesIO()
        image.save(full, format="WEBP", quality=85)
        full_image = full.getvalue()

    thumbnail = image.copy()
    thumbnail.thumbnail((480, 480))

    small = BytesIO()
    thumbnail.save(small, format="WEBP", quality=75)

    return {
        "image": full_image,
        "thumbnail": small.getvalue(),
        "width": image.width,
        "height": image.height,
        "mime_type": "image/webp",
    }