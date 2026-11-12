"""watch progress and channel views

Revision ID: b5e8c1d2a7f4
Revises: 666825b6420a
Create Date: 2026-11-12 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5e8c1d2a7f4'
down_revision: Union[str, Sequence[str], None] = '666825b6420a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('channel_views',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('channel_id', sa.String(length=64), nullable=False),
    sa.Column('at', sa.String(length=40), nullable=False),
    sa.Column('source', sa.String(length=32), nullable=True),
    sa.Column('detail', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_channel_views'))
    )
    with op.batch_alter_table('channel_views', schema=None) as batch_op:
        batch_op.create_index('ix_channel_views_at', ['at'], unique=False)
        batch_op.create_index('ix_channel_views_channel', ['channel_id', 'at'], unique=False)

    with op.batch_alter_table('plays', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('detail', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('rank', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('length', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('watched', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('position', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('outcome', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('updated', sa.String(length=40), nullable=True))
        batch_op.create_index('ix_plays_at', ['at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('plays', schema=None) as batch_op:
        batch_op.drop_index('ix_plays_at')
        batch_op.drop_column('updated')
        batch_op.drop_column('outcome')
        batch_op.drop_column('position')
        batch_op.drop_column('watched')
        batch_op.drop_column('length')
        batch_op.drop_column('rank')
        batch_op.drop_column('detail')
        batch_op.drop_column('source')

    with op.batch_alter_table('channel_views', schema=None) as batch_op:
        batch_op.drop_index('ix_channel_views_channel')
        batch_op.drop_index('ix_channel_views_at')

    op.drop_table('channel_views')
