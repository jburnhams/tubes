"""related channels

Revision ID: 5d1e7a9c3f20
Revises: c34aa161ab66
Create Date: 2026-11-12 05:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d1e7a9c3f20'
down_revision: Union[str, Sequence[str], None] = 'c34aa161ab66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('related_links',
    sa.Column('source_id', sa.String(length=64), nullable=False),
    sa.Column('channel_id', sa.String(length=64), nullable=False),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('handle', sa.String(), nullable=True),
    sa.Column('hits', sa.Integer(), server_default='0', nullable=False),
    sa.Column('featured', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.PrimaryKeyConstraint('source_id', 'channel_id', name=op.f('pk_related_links'))
    )
    with op.batch_alter_table('related_links', schema=None) as batch_op:
        batch_op.create_index('ix_related_links_channel', ['channel_id'], unique=False)

    op.create_table('related_sources',
    sa.Column('channel_id', sa.String(length=64), nullable=False),
    sa.Column('fetched', sa.String(length=40), nullable=False),
    sa.Column('videos', sa.Integer(), server_default='0', nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('channel_id', name=op.f('pk_related_sources'))
    )
    with op.batch_alter_table('suggestions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('suggested_by', sa.Integer(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('related_score', sa.Float(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('suggestions', schema=None) as batch_op:
        batch_op.drop_column('related_score')
        batch_op.drop_column('suggested_by')

    op.drop_table('related_sources')
    with op.batch_alter_table('related_links', schema=None) as batch_op:
        batch_op.drop_index('ix_related_links_channel')

    op.drop_table('related_links')
