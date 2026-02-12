from sqlalchemy import SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Provider(Base):
    __tablename__ = "providers"

    provider_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    provider_code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
