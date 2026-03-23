"""Backward-compat re-exports — actual logic moved to service layer.

- sanitize_filename → app.utils.text_sort
- score_consecutive_transitions → app.services.scoring_helpers
"""

from app.services.scoring_helpers import (
    score_consecutive_transitions as score_consecutive_transitions,
)
from app.utils.text_sort import sanitize_filename as sanitize_filename
