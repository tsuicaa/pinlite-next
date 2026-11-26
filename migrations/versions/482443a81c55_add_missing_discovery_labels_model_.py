"""add missing discovery labels model column

Revision ID: 482443a81c55
Revises: 186803a6cd12
Create Date: 2026-11-26 19:15:03.861342

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '482443a81c55'
down_revision: Union[str, Sequence[str], None] = '186803a6cd12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "media",
        sa.Column("discovery_labels_model", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("media", "discovery_labels_model")