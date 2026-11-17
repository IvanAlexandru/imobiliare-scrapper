import re

def deduplicate(listings):
    output, seen = [], set()
    for x in listings:
        key = (x.source, x.id)
        if key in seen:
            continue
        seen.add(key)
        output.append(x)
    return output

def possible_duplicates(listings):
    # Flag pairs; never discard cross-site listings without an identity guarantee.
    pairs = []
    for i, a in enumerate(listings):
        for b in listings[i + 1:]:
            address = re.sub(r"\W+", " ", a.address.casefold()).strip()
            if (a.source != b.source and len(address) > 10 and re.search(r"\d", address)
                and address == re.sub(r"\W+", " ", b.address.casefold()).strip()
                and a.rooms == b.rooms and a.year == b.year
                and a.usable_area and b.usable_area and abs(a.usable_area-b.usable_area) < 1
                and a.price_eur and b.price_eur and abs(a.price_eur-b.price_eur) < 1000):
                pairs.append((a, b))
    return pairs
