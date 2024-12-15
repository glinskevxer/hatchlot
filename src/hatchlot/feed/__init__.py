"""Feed: what goes in the fish, what it costs, and what comes out the other end.

`feedlot` is the product and its tag, `store` is what is on hand, `ration` is
how much a lot is owed, `feeding` is what was actually put in the water,
`conversion` is what it bought, `medicated` is the part with a vet's name on it,
and `summary` reads the month.
"""

from .conversion import Conversion, cost_per_gain, feed_needed
from .feeding import Feeding, FeedingLog, FeedMethod, feed_by_lot
from .feedlot import Analysis, FeedForm, FeedLot, pellet_for
from .medicated import Drug, Prescription, Withdrawal, inclusion_rate, withdrawal_for
from .ration import RationPlan, daily_ration, feeding_rate, plan_ration
from .store import FeedStore, StoreEntry, StoreEvent
from .summary import FeedSummary, needs_ordering, summarise_feed

__all__ = [
    "Analysis",
    "Conversion",
    "Drug",
    "FeedForm",
    "FeedLot",
    "FeedMethod",
    "FeedStore",
    "FeedSummary",
    "Feeding",
    "FeedingLog",
    "Prescription",
    "RationPlan",
    "StoreEntry",
    "StoreEvent",
    "Withdrawal",
    "cost_per_gain",
    "daily_ration",
    "feed_by_lot",
    "feed_needed",
    "feeding_rate",
    "inclusion_rate",
    "needs_ordering",
    "pellet_for",
    "plan_ration",
    "summarise_feed",
    "withdrawal_for",
]
