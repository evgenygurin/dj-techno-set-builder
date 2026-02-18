"""add pinned, ym_playlist_id, template_name, source_playlist_id

Revision ID: 560f9b4818b6
Revises: 9a7f02f4bdbc
Create Date: 2026-02-18 20:59:24.740851
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '560f9b4818b6'
down_revision: Union[str, None] = '9a7f02f4bdbc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # dj_set_items: add pinned column with default False
    op.add_column(
        'dj_set_items',
        sa.Column('pinned', sa.Boolean(), nullable=False, server_default=sa.text('0')),
    )

    # dj_sets: add unified set builder columns (all nullable, no FK for SQLite compat)
    op.add_column('dj_sets', sa.Column('ym_playlist_id', sa.Integer(), nullable=True))
    op.add_column('dj_sets', sa.Column('template_name', sa.String(length=50), nullable=True))
    op.add_column('dj_sets', sa.Column('source_playlist_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('dj_sets', 'source_playlist_id')
    op.drop_column('dj_sets', 'template_name')
    op.drop_column('dj_sets', 'ym_playlist_id')
    op.drop_column('dj_set_items', 'pinned')
