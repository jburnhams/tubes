"""groups of videos

Revision ID: 8c41f07be2d6
Revises: 2d09e383fc1d
Create Date: 2026-11-25 07:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c41f07be2d6'
down_revision: Union[str, Sequence[str], None] = '2d09e383fc1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('video_groups',
    sa.Column('id', sa.Integer(), autoincrement=False, nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=True),
    sa.Column('named', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_video_groups'))
    )
    op.create_table('video_group_members',
    sa.Column('group_id', sa.Integer(), autoincrement=False, nullable=False),
    sa.Column('video_id', sa.String(length=64), nullable=False),
    sa.Column('score', sa.Float(), server_default='0', nullable=False),
    sa.PrimaryKeyConstraint('group_id', 'video_id', name=op.f('pk_video_group_members'))
    )
    op.create_index('ix_video_group_members_video', 'video_group_members', ['video_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_video_group_members_video', table_name='video_group_members')
    op.drop_table('video_group_members')
    op.drop_table('video_groups')
