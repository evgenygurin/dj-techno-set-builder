from datetime import datetime

from sqlalchemy import CheckConstraint, Float, ForeignKey, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Key(Base):
    __tablename__ = "keys"
    __table_args__ = (
        CheckConstraint(
            "key_code = pitch_class * 2 + mode",
            name="ck_keys_code_deterministic",
        ),
    )

    key_code: Mapped[int] = mapped_column(
        SmallInteger,
        CheckConstraint("key_code BETWEEN 0 AND 23", name="ck_keys_code_range"),
        primary_key=True,
        autoincrement=False,
    )
    pitch_class: Mapped[int] = mapped_column(
        SmallInteger,
        CheckConstraint("pitch_class BETWEEN 0 AND 11", name="ck_keys_pitch_class"),
    )
    mode: Mapped[int] = mapped_column(
        SmallInteger,
        CheckConstraint("mode IN (0, 1)", name="ck_keys_mode"),
    )
    name: Mapped[str] = mapped_column(String(10))
    camelot: Mapped[str | None] = mapped_column(String(5))


class KeyEdge(Base):
    __tablename__ = "key_edges"

    from_key_code: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("keys.key_code"),
        primary_key=True,
    )
    to_key_code: Mapped[int] = mapped_column(
        SmallInteger,
        ForeignKey("keys.key_code"),
        primary_key=True,
    )
    distance: Mapped[float] = mapped_column(
        Float,
        CheckConstraint("distance >= 0", name="ck_key_edges_distance"),
    )
    weight: Mapped[float] = mapped_column(Float)
    rule: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
