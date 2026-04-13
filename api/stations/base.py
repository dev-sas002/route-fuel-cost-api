"""The fuel-price-source seam.

Where prices come from is the other thing a deployment will want to change: a
CSV today, a vendor feed or a partner API tomorrow. A source only has to answer
"give me every station you know about"; the index and the optimiser are written
against :class:`~api.domain.types.Station`, not against the Django ORM.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from api.domain.types import Station


@runtime_checkable
class FuelPriceSource(Protocol):
    """Supplies the station catalogue used to build the spatial index."""

    #: Stable short name, used in cache keys and logs.
    name: str

    def load(self) -> Iterable[Station]:
        """Yield every known station with its current price."""
        ...
