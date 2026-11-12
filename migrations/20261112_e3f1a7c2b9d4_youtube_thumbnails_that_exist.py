"""youtube thumbnails that exist

Revision ID: e3f1a7c2b9d4
Revises: 7a2c4e91d0b3
Create Date: 2026-11-12 06:30:00.000000

Data only. youtube.best_thumbnail used to keep the largest size the Data API listed, which for many uploads since 2026-11 is `fhddefault`,
`qhddefault` or `uhddefault`: i.ytimg.com answers 404 for those, so the card was blank. `maxresdefault` was there for every one tried, and
the next sync of a channel would only mend the videos it reads again, so the stored URLs are rewritten here. `replace` runs on SQLite and
Postgres alike. Not undone: the old URLs never loaded.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e3f1a7c2b9d4'
down_revision: Union[str, Sequence[str], None] = '7a2c4e91d0b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BROKEN = ('fhddefault', 'qhddefault', 'uhddefault')


def upgrade() -> None:
    for name in BROKEN:
        op.execute(f"UPDATE videos SET thumbnail = replace(thumbnail, '/{name}.', '/maxresdefault.') WHERE thumbnail LIKE '%/{name}.%'")


def downgrade() -> None:
    pass
