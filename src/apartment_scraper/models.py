from dataclasses import dataclass, field
from datetime import datetime, timezone

@dataclass
class Listing:
    source: str
    id: str
    url: str
    title: str = ""
    price_eur: float | None = None
    rooms: int | None = None
    year: int | None = None
    usable_area: float | None = None
    floor: str | None = None
    total_floors: int | None = None
    address: str = ""
    latitude: float | None = None
    longitude: float | None = None
    precise_location: bool = False
    seller: str | None = None
    published: str | None = None
    updated: str | None = None
    description: str = ""
    city: str = ""
    transaction: str = ""
    property_type: str = ""
    scanned: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    @property
    def price_m2(self):
        return self.price_eur / self.usable_area if self.price_eur and self.usable_area and self.usable_area > 0 else None

@dataclass
class SourceResult:
    source: str
    status: str = "failed"
    examined: int = 0
    pages: int = 0
    listings: list[Listing] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
