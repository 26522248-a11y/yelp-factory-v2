"""Human-like browser interactions.

All async timing helpers respect ``YF_HUMAN_TIME_SCALE``:
  - ``1.0`` (default) keeps production cadence.
  - ``0.0`` collapses every sleep/idle/dwell/typing delay to zero, used by tests.
"""

from human.mouse import human_click, move_to, read_pause
from human.scroll import scroll_page
from human.timing import idle, sleep_s
from human.typing import human_type, set_value_native

__all__ = [
    "human_click",
    "human_type",
    "idle",
    "move_to",
    "read_pause",
    "scroll_page",
    "set_value_native",
    "sleep_s",
]
