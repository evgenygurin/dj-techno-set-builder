from app.schemas.base import BaseSchema


class KeyRead(BaseSchema):
    key_code: int
    pitch_class: int
    mode: int
    name: str
    camelot: str | None


class KeyList(BaseSchema):
    items: list[KeyRead]
    total: int
