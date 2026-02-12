"""Domain enums matching schema_v6.sql smallint CHECK constraints.

These are for documentation and app-level validation.
The database stores raw smallint/text values.
"""

from enum import IntEnum, StrEnum


class ArtistRole(IntEnum):
    PRIMARY = 0
    FEATURED = 1
    REMIXER = 2


class SectionType(IntEnum):
    INTRO = 0
    BUILDUP = 1
    DROP = 2
    BREAKDOWN = 3
    OUTRO = 4
    BREAK = 5
    INST = 6
    VERSE = 7
    CHORUS = 8
    BRIDGE = 9
    SOLO = 10
    UNKNOWN = 11


class CueKind(IntEnum):
    CUE = 0
    LOAD = 1
    GRID = 2
    FADE_IN = 3
    FADE_OUT = 4
    LOOP_IN = 5
    LOOP_OUT = 6
    MEMORY = 7


class SourceApp(IntEnum):
    TRAKTOR = 1
    REKORDBOX = 2
    DJAY = 3
    IMPORT = 4
    GENERATED = 5


class TargetApp(IntEnum):
    TRAKTOR = 1
    REKORDBOX = 2
    DJAY = 3


class AssetType(IntEnum):
    FULL_MIX = 0
    DRUMS_STEM = 1
    BASS_STEM = 2
    VOCALS_STEM = 3
    OTHER_STEM = 4
    PREVIEW_CLIP = 5


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class FeedbackType(StrEnum):
    MANUAL = "manual"
    LIVE_CROWD = "live_crowd"
    A_B_TEST = "a_b_test"
