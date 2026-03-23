import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.catalog import Track
from app.core.models.embeddings import EmbeddingType, TrackEmbedding
from app.core.models.runs import FeatureExtractionRun


async def test_create_embedding_type(session: AsyncSession) -> None:
    et = EmbeddingType(embedding_type="groove", dim=128, model_name="essentia-effnet")
    session.add(et)
    await session.flush()
    assert et.embedding_type == "groove"


async def test_embedding_type_dim_positive(session: AsyncSession) -> None:
    """dim must be > 0."""
    et = EmbeddingType(embedding_type="bad", dim=0)
    session.add(et)
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_create_track_embedding(session: AsyncSession) -> None:
    et = EmbeddingType(embedding_type="groove", dim=128)
    track = Track(title="T", duration_ms=300000)
    run = FeatureExtractionRun(pipeline_name="test", pipeline_version="1.0.0")
    session.add_all([et, track, run])
    await session.flush()
    te = TrackEmbedding(
        track_id=track.track_id,
        run_id=run.run_id,
        embedding_type="groove",
        vector="[0.1,0.2,0.3]",
    )
    session.add(te)
    await session.flush()
    assert te.embedding_id is not None


async def test_track_embedding_unique(session: AsyncSession) -> None:
    """(track_id, embedding_type, run_id) must be unique."""
    et = EmbeddingType(embedding_type="groove", dim=128)
    track = Track(title="T", duration_ms=300000)
    run = FeatureExtractionRun(pipeline_name="test", pipeline_version="1.0.0")
    session.add_all([et, track, run])
    await session.flush()
    te1 = TrackEmbedding(
        track_id=track.track_id,
        run_id=run.run_id,
        embedding_type="groove",
        vector="[0.1]",
    )
    te2 = TrackEmbedding(
        track_id=track.track_id,
        run_id=run.run_id,
        embedding_type="groove",
        vector="[0.2]",
    )
    session.add_all([te1, te2])
    with pytest.raises(IntegrityError):
        await session.flush()
