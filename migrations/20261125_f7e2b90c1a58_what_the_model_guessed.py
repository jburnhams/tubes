"""what the model guessed

Revision ID: f7e2b90c1a58
Revises: d0b6a1f4c953
Create Date: 2026-11-25 12:40:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7e2b90c1a58'
down_revision: Union[str, Sequence[str], None] = 'd0b6a1f4c953'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('video_extents') as batch_op:
        batch_op.add_column(sa.Column('guess', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('video_extents') as batch_op:
        batch_op.drop_column('guess')
