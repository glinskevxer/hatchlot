"""Marking: telling one release group from another after it has gone.

`mark` is what the fish carries and the code that identifies it, `run` is the
day at the trailer and the check that has to follow it, and `summary` adds the
runs up into the numbers on the release report.
"""

from .mark import MarkPlan, MarkType, TagCode, is_double_index, mark_rate
from .run import MarkingRun, QualityCheck, RunState, require_accepted
from .summary import GroupMarking, expanded_tags, summarise_group, tags_needed

__all__ = [
    "GroupMarking",
    "MarkPlan",
    "MarkType",
    "MarkingRun",
    "QualityCheck",
    "RunState",
    "TagCode",
    "expanded_tags",
    "is_double_index",
    "mark_rate",
    "require_accepted",
    "summarise_group",
    "tags_needed",
]
