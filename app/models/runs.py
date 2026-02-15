from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FeatureExtractionRun(Base):
    __tablename__ = "feature_extraction_runs"

    run_id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_name: Mapped[str] = mapped_column(String(200))
    pipeline_version: Mapped[str] = mapped_column(String(50))
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    code_ref: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint(
            "status IN ('running','completed','failed')",
            name="ck_feature_runs_status",
        ),
        default="running",
        server_default=text("'running'"),
    )
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class TransitionRun(Base):
    __tablename__ = "transition_runs"

    run_id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_name: Mapped[str] = mapped_column(String(200))
    pipeline_version: Mapped[str] = mapped_column(String(50))
    weights: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    constraints: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint(
            "status IN ('running','completed','failed')",
            name="ck_transition_runs_status",
        ),
        default="running",
        server_default=text("'running'"),
    )
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
