from datetime import datetime
from zoneinfo import ZoneInfo
from html import escape
from .deduplication import possible_duplicates

def render(results, confirmed, unverified, subject):
    stamp = datetime.now(ZoneInfo("Europe/Bucharest")).strftime("%Y-%m-%d %H:%M %Z")
    overall = "FAILED" if all(r.status == "failed" for r in results) else ("COMPLETE" if all(r.status == "success" for r in results) else "PARTIAL")
    lines = [f"{subject} — {overall}", f"Scan: {stamp}",
             f"Confirmed matches: {len(confirmed)}", f"Location-unverified candidates: {len(unverified)}"]
    for r in results:
        lines.append(f"{r.source}: {r.status}; {r.examined} unique listings examined, {len(r.listings)} details parsed, {r.pages} search pages")
        lines.extend(f"Warning: {w}" for w in r.warnings)
    pairs = possible_duplicates(confirmed + unverified)
    for a, b in pairs:
        lines.append(f"Possible cross-site duplicate (retained for review): {a.url} / {b.url}")
    header = "<br>".join(escape(s) for s in lines)
    sections = []
    for label, items in (("Confirmed matches", confirmed), ("Location unverified — polygon inclusion unknown", unverified)):
        lines.append("\n" + label)
        rows = []
        for x in items:
            values = [x.title, x.source, f"€{x.price_eur:,.0f}", str(x.rooms),
                      f"{x.usable_area:g}" if x.usable_area else "Unknown",
                      f"{x.price_m2:,.0f}" if x.price_m2 else "Unknown", str(x.year),
                      x.address or "Unknown", x.floor or "Unknown", str(x.total_floors or "Unknown"),
                      x.seller or "Unknown", x.published or "Unknown", x.updated or "Unknown"]
            lines.append(" | ".join(values) + "\n" + x.url)
            rows.append('<tr><td><a href="' + escape(x.url, quote=True) + '">' + escape(values[0]) + '</a></td>' +
                        ''.join('<td>' + escape(v) + '</td>' for v in values[1:]) + '</tr>')
        if not items:
            lines.append("No confirmed matches found." if label == "Confirmed matches" else "No candidates.")
        headings = ["Apartment", "Source", "Price EUR", "Rooms", "Usable m²", "€/usable m²", "Year", "Location", "Floor", "Total floors", "Seller", "Published (site)", "Updated (site)"]
        sections.append('<h2>' + escape(label) + '</h2><div style="overflow-x:auto"><table><thead><tr>' +
                        ''.join('<th>' + escape(h) + '</th>' for h in headings) + '</tr></thead><tbody>' +
                        ''.join(rows) + '</tbody></table></div>' + ('<p>No listings.</p>' if not items else ''))
    html = ('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<style>body{font:15px Arial;color:#182333;margin:16px}td,th{padding:8px;text-align:left;border-bottom:1px solid #ddd}table{border-collapse:collapse}h2{font-size:19px}</style>'
            '</head><body><p>' + header + '</p>' + ''.join(sections) +
            '<p>Stateless scan. No historical price-change or first-discovered claims. Site publication dates may reflect relisting. EUR only; non-EUR prices excluded.</p></body></html>')
    return f"[{overall}] {subject}", html, "\n".join(lines)
