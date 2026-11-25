"""how much of a thing a video is

Revision ID: d0b6a1f4c953
Revises: 8c41f07be2d6
Create Date: 2026-11-25 11:50:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0b6a1f4c953'
down_revision: Union[str, Sequence[str], None] = '8c41f07be2d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('video_extents',
    sa.Column('video_id', sa.String(length=64), nullable=False),
    sa.Column('extent', sa.String(length=24), nullable=False),
    sa.Column('said_by', sa.String(length=16), nullable=False),
    sa.Column('at', sa.String(length=40), nullable=False),
    sa.PrimaryKeyConstraint('video_id', name=op.f('pk_video_extents'))
    )
    op.create_index('ix_video_extents_extent', 'video_extents', ['extent'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_video_extents_extent', table_name='video_extents')
    op.drop_table('video_extents')
