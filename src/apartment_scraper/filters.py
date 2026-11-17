import math
from urllib.parse import urlsplit
from shapely.geometry import Point, shape

def numeric(value):
    try:
        n = float(str(value).replace("\u00a0", "").replace(" ", "").replace(",", "."))
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None

def eur(value, currency):
    # No implicit FX: non-EUR prices remain unknown and are excluded.
    return numeric(value) if currency == "EUR" else None

def usable_area(value, kind="usable"):
    n = numeric(value)
    return n if kind == "usable" and n is not None and n > 0 else None

def qualifies(x, f):
    if not all(isinstance(v, str) for v in (x.id, x.url, x.title, x.source)):
        return False
    price, year, rooms = numeric(x.price_eur), numeric(x.year), numeric(x.rooms)
    return bool(x.id and x.url and urlsplit(x.url).scheme == "https"
                and x.city == f["city"] and x.transaction == f["transaction"]
                and x.property_type == f["property_type"]
                and price is not None and 0 < price < f["max_price_eur"]
                and year is not None and year.is_integer() and f["min_year"] <= year <= 2100
                and rooms in f["rooms"])

def partition(listings, f):
    confirmed, unverified = [], []
    polygon = shape(f["polygon"])
    for x in listings:
        if not qualifies(x, f):
            continue
        lat, lon = numeric(x.latitude), numeric(x.longitude)
        if not x.precise_location or lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            unverified.append(x)
        elif polygon.covers(Point(lon, lat)):
            confirmed.append(x)
    confirmed.sort(key=lambda x: x.price_m2 if x.price_m2 is not None else float("inf"))
    return confirmed, unverified
