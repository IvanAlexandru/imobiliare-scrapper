import argparse
import logging
from .config import load
from .models import SourceResult
from .scrapers import storia_ro, imobiliare_ro
from .filters import partition
from .deduplication import deduplicate
from .reporting import render
from .email_sender import send

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--smoke", action="store_true", help="At most one search page and two details; no email")
    parser.add_argument("--dry-run", action="store_true", help="Scan without emailing; logs only counts/status")
    args = parser.parse_args()
    config = load(args.config)
    logging.basicConfig(level=config["logging_level"], format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    results = []
    for name, module in (("storia_ro", storia_ro), ("imobiliare_ro", imobiliare_ro)):
        if not config["websites"].get(name):
            continue
        try:
            result = module.scan(config, smoke=args.smoke)
        except Exception:
            result = SourceResult(name, warnings=["Unexpected source failure"])
        results.append(result)
        logging.info("%s: %s; examined=%d parsed=%d pages=%d", name, result.status, result.examined, len(result.listings), result.pages)
        for warning in result.warnings:
            logging.warning("%s: %s", name, warning)
    matches, unverified = partition(deduplicate([x for r in results for x in r.listings]), config["filters"])
    subject, html, text = render(results, matches, unverified, config["email"]["subject"])
    logging.info("confirmed=%d location_unverified=%d", len(matches), len(unverified))
    if not (args.smoke or args.dry_run):
        try:
            send(subject, html, text)
        except RuntimeError as e:
            logging.error("%s", e)
            raise SystemExit(1)
    raise SystemExit(1 if all(r.status == "failed" for r in results) else 0)

if __name__ == "__main__":
    main()
