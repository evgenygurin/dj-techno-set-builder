from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models.base import Base


class EmbeddingType(Base):
    __tablename__ = "embedding_types"

    embedding_type: Mapped[str] = mapped_column(String(100), primary_key=True)
    dim: Mapped[int] = mapped_column(
        CheckConstraint("dim > 0", name="ck_embedding_types_dim"),
    )
    model_name: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class TrackEmbedding(Base):
    __tablename__ = "track_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "track_id",
            "embedding_type",
            "run_id",
            name="uq_embeddings_track_type_run",
        ),
    )

    embedding_id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.track_id", ondelete="CASCADE"))
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("feature_extraction_runs.run_id", ondelete="CASCADE"),
    )
    embedding_type: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("embedding_types.embedding_type"),
    )
    # vector column: pgvector in PG, String placeholder for SQLite
    vector: Mapped[str] = mapped_column(String(10000))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
