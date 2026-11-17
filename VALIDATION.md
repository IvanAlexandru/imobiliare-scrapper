# Validation — 16 November 2026

## Executed

- `python -m pytest -q`: **43 passed**. All HTTP in tests is mocked. Covers polygon interior/exterior/boundary, strict €300,000 cutoff, rooms, minimum year, missing/malformed fields, EUR-only normalization, usable area, ordering, conservative duplicates, both parsers and pagination, failure handling, blocked/robots-disallowed paths, wildcard/end-anchor Allow precedence, user-agent groups, percent encoding, crawl delay, exponential retries, HTML escaping, plain text report, email API request/errors, all-failed/partial process exit behavior.
- `python -m pip_audit -r requirements.lock --disable-pip --cache-dir /workspace/work/audit-cache`: **No known vulnerabilities found** in locked runtime dependencies. This does not prove absence of unknown vulnerabilities.
- Both workflow files parsed as YAML and minimal `contents: read` permissions checked. Workflow execution on GitHub itself has not been tested.
- Runtime/test dependencies resolved into full hash lockfiles and installed in an isolated Python 3.12 environment.

## Controlled live observations

### Storia.ro

- Public robots.txt: HTTP 200. Search/detail paths used were permitted.
- Bucharest apartment-for-sale search: HTTP 200, public `__NEXT_DATA__` parsed; 684 advertised pages at inspection.
- Page 2: HTTP 200; payload currentPage=2, 35 returned cards, 36 configured items per page. Pagination advancement verified rather than inferred from URLs.
- Application smoke scan: one search page and **two detail pages parsed**, explicitly PARTIAL after reaching the smoke limit. It reports three cards examined because it encounters the next card before stopping detail requests. No live email.
- Footer help/legal pages: HTTP 200 but JavaScript application shells; substantive terms could not be confirmed from these responses. Review current terms before production use.

### Imobiliare.ro

- Initial standard-library requests for robots/search: HTTP 403. No retry with evasion, CAPTCHA solver, credentials or proxy was performed.
- Subsequent ordinary HTTPX requests using the declared application user agent: robots, public search and detail HTML returned HTTP 200. Access is variable, and may differ on GitHub runner IPs.
- Verified public Inertia `data-page` search and detail structures. A retrieved real detail yielded rooms=3, construction year=2026, displayed asking price EUR 298,870, usable interior area 78.27 m², floor/total floors and explicit source pin precision. This example demonstrates extraction, not a claim of a qualifying apartment.
- Application smoke scan: one search page and **two detail pages parsed**, explicitly PARTIAL at the smoke limit.
- Live page 2: payload currentPage=2, 30 result cards, lastPage=333. The search result window does not cover the advertised total.
- Current robots rules allow query pages 2–10 and disallow later query pagination. Page 11 was checked by the client and **refused before a network request**. Default runs stop at that policy boundary and report partial coverage.
- Public terms retrieved and inspected. The explicit scraping clause observed concerns ImoAI responses; no ImoAI or private API was used. This inspection is not a guarantee that terms will remain unchanged or permit every intended use.

No controls were bypassed. Live responses were used only for inspection and parser validation. The shipped HTML fixtures are synthetic minimal examples of inspected schemas; actual listings, session IDs and user tokens are excluded.

## Remaining integration boundaries

- No exhaustive city scan was performed. Default page/detail caps and website access policies intentionally limit coverage.
- No real Resend API key was supplied; live delivery, DNS verification and inbox placement remain untested. Email calls and failure behavior are tested with mocks.
- No GitHub repository was created, pushed or scheduled; the supplied workflows still need installation in your private repository.
- Source coordinate precision is asserted by the source, not independently measured. Missing/obfuscated positions stay unverified.
- Non-EUR prices are excluded rather than converted. Displayed asking prices may include or exclude VAT; no taxes, commissions or parking extras are estimated.
- Dates and floors remain missing when public structured information is unavailable; no login-only date/history information is retrieved.
- GitHub cron timing is best effort. Runner termination at the job timeout prevents report delivery for that invocation.
- Site layouts, legal conditions, robots policies and access availability can change; run the controlled smoke command when diagnosing a problem.

## Files supplied

- `.github/workflows/daily-scraper.yml`, `.github/workflows/tests.yml`
- `src/apartment_scraper/{config,models,http,robots,filters,deduplication,reporting,email_sender,main}.py` and package initializers
- `src/apartment_scraper/scrapers/{imobiliare_ro,storia_ro}.py`
- `tests/test_project.py` and five synthetic HTML fixtures
- `config.yaml`, `.env.example`, `.gitignore`, `pyproject.toml`
- `requirements.lock`, `requirements-dev.lock`, `README.md`, `VALIDATION.md`

The README includes exact local execution, Resend setup, private GitHub repository/Secrets setup, manual triggering, schedule behavior, logging and troubleshooting steps.
