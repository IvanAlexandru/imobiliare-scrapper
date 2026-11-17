import json
from bs4 import BeautifulSoup
from ..http import Client, AccessError
from ..models import Listing, SourceResult
from ..filters import numeric, eur, usable_area

BASE = "https://www.storia.ro"
SEARCH = BASE + "/ro/rezultate/vanzare/apartament/bucuresti"

def payload(html):
    node = BeautifulSoup(html, "html.parser").find("script", id="__NEXT_DATA__")
    if node is None:
        raise ValueError("Missing __NEXT_DATA__; layout change or access challenge")
    return json.loads(node.string)["props"]["pageProps"]

def search_page(html):
    data = payload(html)["data"]["searchAds"]
    items, p = data["items"], data["pagination"]
    if not isinstance(items, list) or not isinstance(p["totalPages"], int):
        raise ValueError("Invalid search schema")
    if not items and p["totalItems"] != 0:
        raise ValueError("Empty page despite nonzero result count")
    return items, p

def parse_listing(html):
    a = payload(html)["ad"]
    attrs = a["attributes"]
    chars = {c["key"]: c for c in a["characteristics"]}
    price = chars.get("price", {})
    loc = a.get("location") or {}
    coords = loc.get("coordinates") or {}
    street = (loc.get("address") or {}).get("street") or {}
    areas = chars.get("m", {})
    city = "Bucuresti" if any(v.get("id") == "bucuresti" for v in (loc.get("reverseGeocoding") or {}).get("locations", [])) else ""
    category = a.get("adCategory") or {}
    nrooms, year = numeric(attrs.get("rooms_num")), numeric(attrs.get("build_year"))
    return Listing(source="storia_ro", id=str(a["id"]), url=a["url"], title=a["title"],
        price_eur=eur(price.get("value"), price.get("currency")),
        rooms=int(nrooms) if nrooms is not None and nrooms.is_integer() else None,
        year=int(year) if year is not None and year.is_integer() else None,
        usable_area=usable_area(areas.get("value")), floor=attrs.get("floor_no"),
        total_floors=int(attrs["building_floors_num"]) if str(attrs.get("building_floors_num", "")).isdigit() else None,
        address=" ".join(str(street[k]) for k in ("name", "number") if street.get(k)),
        latitude=numeric(coords.get("latitude")), longitude=numeric(coords.get("longitude")),
        precise_location=(loc.get("mapDetails") or {}).get("radius") == 0,
        seller={"AGENCY":"agency", "PRIVATE":"owner"}.get(a.get("advertType")),
        published=a.get("createdAt"), updated=a.get("modifiedAt"),
        description=BeautifulSoup(a.get("description", ""), "html.parser").get_text(" "),
        city=city, transaction=category.get("type", ""), property_type=category.get("name", ""))

def scan(config, smoke=False):
    result = SourceResult("storia_ro")
    client = Client("www.storia.ro", config["http"])
    seen, detail_count, parsed = set(), 0, 0
    try:
        limit = 1 if smoke else config["http"]["max_pages"]
        for page in range(1, limit + 1):
            items, pagination = search_page(client.get(SEARCH + f"?page={page}"))
            if pagination["currentPage"] != page:
                raise ValueError("Pagination did not advance")
            result.pages += 1
            fresh = [i for i in items if str(i["id"]) not in seen]
            if items and not fresh:
                raise ValueError("Repeated page; pagination stalled")
            for item in fresh:
                seen.add(str(item["id"]))
                result.examined += 1
                if not smoke:
                    known_rooms = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6}.get(item.get("roomsNumber"))
                    price = item.get("totalPrice") or {}
                    known_price = eur(price.get("value"), price.get("currency"))
                    if known_rooms is not None and known_rooms not in config["filters"]["rooms"]:
                        continue
                    if known_price is not None and known_price >= config["filters"]["max_price_eur"]:
                        continue
                # Fetch details; search cards do not contain construction year reliably.
                if detail_count >= (2 if smoke else config["http"]["max_details"]):
                    result.warnings.append("Detail limit reached; coverage incomplete")
                    result.status = "partial" if parsed else "failed"
                    return result
                detail_count += 1
                try:
                    x = parse_listing(client.get(BASE + "/ro/oferta/" + item["slug"]))
                    result.listings.append(x)
                    parsed += 1
                except AccessError:
                    raise
                except (KeyError, TypeError, ValueError):
                    result.warnings.append("Listing schema invalid or incomplete; one detail skipped")
            if page >= pagination["totalPages"]:
                result.status = ("failed" if result.examined and not parsed else "partial") if result.warnings else "success"
                return result
        result.warnings.append("Page limit reached; coverage incomplete")
        result.status = "partial" if parsed else "failed"
    except Exception as exc:
        result.status = "partial" if parsed else "failed"
        result.warnings.append(str(exc) if isinstance(exc, (AccessError, ValueError)) else type(exc).__name__ + ": source request/parser failed")
    finally:
        client.close()
    return result
