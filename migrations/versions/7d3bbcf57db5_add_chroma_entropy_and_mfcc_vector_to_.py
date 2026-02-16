"""add chroma_entropy and mfcc_vector to track_audio_features_computed

Revision ID: 7d3bbcf57db5
Revises: 
Create Date: 2026-02-16 15:57:39.206149
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d3bbcf57db5'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "track_audio_features_computed",
        sa.Column("chroma_entropy", sa.Float(), nullable=True),
    )
    op.add_column(
        "track_audio_features_computed",
        sa.Column("mfcc_vector", sa.String(500), nullable=True),
    )
    # NOTE: CHECK constraint ck_taf_chroma_entropy is defined in the ORM model.
    # PostgreSQL will enforce it on new tables; SQLite ignores inline CHECKs anyway.
    # Skipping op.create_check_constraint() for SQLite compat.


def downgrade() -> None:
    op.drop_column("track_audio_features_computed", "mfcc_vector")
    op.drop_column("track_audio_features_computed", "chroma_entropy")
