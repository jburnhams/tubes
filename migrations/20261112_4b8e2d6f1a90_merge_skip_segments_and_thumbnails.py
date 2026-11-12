"""merge skip segments and thumbnails

Two branches merged into main the same morning each added a migration after 9992af3c9c62, which left Alembic with two heads (so
`upgrade head` refused to run). This joins them without changing either, so a database that already has one, both or neither of them
upgrades the same way.

Revision ID: 4b8e2d6f1a90
Revises: 1df140210d37, e3f1a7c2b9d4
Create Date: 2026-11-12 07:50:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '4b8e2d6f1a90'
down_revision: Union[str, Sequence[str], None] = ('1df140210d37', 'e3f1a7c2b9d4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Nothing to change: this only joins the two heads."""


def downgrade() -> None:
    """Nothing to change: this only joins the two heads."""
