from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from models import Tag, PinTag

def normalize_tags(values):
    if not isinstance(values, list) or len(values) > 20:
        raise ValueError("Maximum 20 tags")

    names = set()

    for value in values:
        if not isinstance(value, str):
            raise ValueError("Tags must be text")

        name = " ".join(value.split()).casefold()

        if not 1 <= len(name) <= 80:
            raise ValueError("Each tag must be 1-80 charactes")

        names.add(name)

    return sorted(names)

def get_tags(db, pin_id):
    return list(db.scalars(
        select(Tag.name)
        .join(PinTag, PinTag.tag_id == Tag.id)
        .where(PinTag.pin_id == pin_id)
        .order_by(Tag.name)
    ))

def replace_tags(db, pin_id, names):
    db.execute(delete(PinTag).where(PinTag.pin_id == pin_id))

    if not names:
        return

    db.execute(
        insert(Tag)
        .values([{"name": name} for name in names])
        .on_conflict_do_nothing(index_elements=["name"])
    )

    tag_ids = list(db.scalars(
        select(Tag.id).where(Tag.name.in_(names))
    ))

    db.execute(
        insert(PinTag),
        [{"pin_id": pin_id, "tag_id": tag_id} for tag_id in tag_ids],
    )