"""add sync fields to dj_playlists

Revision ID: bb82a1eb7f30
Revises: 560f9b4818b6
Create Date: 2026-02-20 17:56:55.070838
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bb82a1eb7f30'
down_revision: Union[str, None] = '560f9b4818b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('dj_playlists', sa.Column('source_of_truth', sa.String(length=20), server_default='local', nullable=False))
    op.add_column('dj_playlists', sa.Column('platform_ids', sa.JSON(), nullable=True))
    # Note: source_playlist_id FK on dj_sets intentionally skipped for SQLite compat


def downgrade() -> None:
    op.drop_column('dj_playlists', 'platform_ids')
    op.drop_column('dj_playlists', 'source_of_truth')
