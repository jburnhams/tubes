"""pasted suggestions

Revision ID: 7a2c4e91d0b3
Revises: 5d1e7a9c3f20
Create Date: 2026-11-12 05:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a2c4e91d0b3'
down_revision: Union[str, Sequence[str], None] = '5d1e7a9c3f20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('suggestions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('platform', sa.String(length=16), server_default='youtube', nullable=False))
        batch_op.add_column(sa.Column('pasted', sa.String(length=40), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('suggestions', schema=None) as batch_op:
        batch_op.drop_column('pasted')
        batch_op.drop_column('platform')
