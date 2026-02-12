"""Reusable Pydantic constrained types and helpers."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, StringConstraints

PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
UnitFloat = Annotated[float, Field(ge=0.0, le=1.0)]
NonNegativeFloat = Annotated[float, Field(ge=0.0)]
BpmFloat = Annotated[float, Field(ge=20.0, le=300.0)]

SourceApp = Annotated[int, Field(ge=1, le=5)]
TargetApp = Annotated[int, Field(ge=1, le=3)]

HotcueIndex = Annotated[int, Field(ge=0, le=15)]
CueKind = Annotated[int, Field(ge=0, le=7)]
ColorRGB = Annotated[int, Field(ge=0, le=16_777_215)]
KeyCode = Annotated[int, Field(ge=0, le=23)]

ProviderCountryCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        min_length=2,
        max_length=2,
        pattern=r"^[A-Z]{2}$",
    ),
]
