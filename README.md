# Bucharest apartment monitor

A Python 3.12 stateless batch application: inspect public sources, parse listings, filter in memory, send one Resend email, exit. No database, listing history, paid scraping service, proxies, browser automation, downloaded code, or stored reports.

**Current feasibility:** Both Storia and Imobiliare public search/detail HTML were inspected and their parsers tested live on 16 November 2026. Initial Imobiliare requests returned 403; subsequent ordinary requests with the application's declared user agent returned public HTML. No challenge was solved or access control bypassed. Both adapters remain fail-closed whenever access is restricted. Coverage is bounded and must not be treated as exhaustive.

## Windows (PowerShell)

Use Python 3.12 installed from python.org, with the Python launcher enabled.
Run these commands from this project directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pytest -q
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m apartment_scraper.main --smoke
```

Activation is not required. The pinned tzdata dependency supplies the timezone
database that Windows does not normally include. The other local setup command
examples below use POSIX shell syntax; use `$env:VARIABLE = "value"` for secrets
in PowerShell. No secrets are needed for tests or the smoke command.

## Local setup

From this directory, use Python 3.12:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.lock
python -m pytest -q
PYTHONPATH=src python -m apartment_scraper.main --smoke
```

For production dependencies only, install `requirements.lock` instead. Run from the project root with `PYTHONPATH=src`; no editable install or build-time downloads are needed.

The smoke command performs at most one Storia search request and two detail requests, and at most one Imobiliare search page/two details, plus robots checks. It sends no email and logs only counts/status/warnings. Its limits intentionally produce PARTIAL coverage. Exit 1 means every enabled source failed. A source with parsed data plus a coverage limit returns partial; inspect the status, not just the exit code.

For a normal scan without delivery:

```bash
PYTHONPATH=src python -m apartment_scraper.main --dry-run
```

For a scan and email, set these variables through your shell or secret manager:

```bash
export RESEND_API_KEY='your-key'
export REPORT_EMAIL_TO='you@example.com'
export REPORT_EMAIL_FROM='Apartment Report <reports@your-verified-domain.example>'
PYTHONPATH=src python -m apartment_scraper.main
```

`.env.example` documents the names; the application does not automatically load `.env`. Do not paste secrets into terminal commands on shared systems or commit them. HTML and plain text are sent together. No email is sent by tests or smoke scans. Email authentication and actual delivery require your Resend setup and were not tested with live credentials.

## Exact search rules

`config.yaml` specifies Bucharest sale apartments, both seller types, 3 or 4 rooms, structured construction year >=2016, and price strictly less than EUR 300,000. There is no area restriction. Missing or invalid required data fails eligibility; unknown construction year never qualifies. Source apartment/sale/city fields are checked, not inferred from a title.

The exact supplied GeoJSON polygon is checked using Shapely `covers`, including its boundary. Coordinate order is longitude, latitude. A bounding box or neighborhood never replaces the polygon. A finite coordinate pair and explicit source precision (`mapDetails.radius == 0` for Storia; `hideExactLocation == false` for Imobiliare) are required for confirmed inclusion. Missing/obfuscated coordinates, nonzero radius, or missing precision metadata produce a separate location-unverified section if the other rules pass. These are source-reported pins, not independently surveyed locations. Precise coordinates outside the polygon are rejected.

Asking price is the publicly displayed price, which may include or exclude VAT as specified by the advertiser; acquisition extras are not estimated. Only EUR prices are accepted. **There is no FX conversion** or undocumented exchange rate: non-EUR listings have unknown EUR price and are excluded. Structured Storia `characteristics.m` is mapped to usable area, as verified against the site's usable-area presentation during inspection. For Imobiliare, only summary `usable_surface` is used; the distinct specification “Suprafață utilă totală” is not substituted. No built area, terrace, or balcony area is added. Missing usable area is allowed; its €/m² is unknown and sorts last. Price per m² is calculated from asking price and usable area, never taken from gross area.

Fields available in inspected structured data are extracted: source, ID, URL, title, EUR asking price, rooms, usable area, year, floor, total floors when explicitly supplied, street, coordinates, source precision, seller type, dates, description and UTC scan time. Missing fields remain unknown. AI enrichment is deliberately not used to invent floor counts or other facts. Storia `createdAt` and `modifiedAt`, and Imobiliare public listed/updated labels, are included with their source meaning; publication may reflect relisting. No first-seen-today or historical price-reduction claims are made.

Within a run, duplicate source IDs are removed. Conservative cross-source detection requires the same numbered street address, rooms, year, close usable area and price. These are flagged as possible duplicates for review, retained as separate offers, and counted as offers. Similar area and price alone never merge homes. Imobiliare neighborhood-only address labels usually lack the numbered street needed for a cross-site flag.

## Coverage, rate and failure policy

Storia uses the observed public Next.js `__NEXT_DATA__` search/detail payload; Imobiliare uses public Inertia `data-page` HTML. Neither uses hidden APIs. Each search page's `currentPage` is validated against the requested page. Repeated pages, missing payloads, invalid schemas and unexpected empty pages cause warnings/failure. Search cards with known disqualifying rooms or EUR price are skipped before requesting details; missing values are checked on detail pages.

Defaults: sequential requests (concurrency 1), at least 2 seconds between request starts per host, 25-second timeouts, 3 attempts with exponential backoff for network/5xx failures, up to 30 search pages and 400 detail requests. These caps keep daily cost/runtime bounded within the 45-minute job budget under normal network conditions. Timeouts/retries can still exhaust that budget. A timeout killed by GitHub cannot finish an email: inspect workflow notifications/logs.

Storia had 684 city result pages at inspection; Imobiliare exposed a 333-page result window smaller than its advertised total. Imobiliare robots currently permit query pagination pages 2–10 and disallow later pages; the adapter attempts normal pagination and stops before requesting a disallowed URL, with an explicit incomplete-coverage warning. Robots wildcard/end-anchor and longest-specific-match Allow precedence are implemented and tested. No alternative URL is used to evade those rules. **Default coverage is intentionally incomplete**, not a daily exhaustive scan. Search ordering can change during a scan. Every cap is reported; this application makes no guarantee of finding all qualifying apartments. Increase limits only after considering permitted rates and runtime; broad exhaustive scans can take too long for this workflow. Source-side filters can be added after verifying their current URLs and response semantics.

Each adapter is isolated so one failure does not stop the other. Every regular invocation attempts one report, including when no listings match or all sources fail. Overall report labels:

- COMPLETE: every enabled source completed its requested coverage without warnings.
- PARTIAL: at least one source provided usable results, but a source failed or coverage is incomplete.
- FAILED: every enabled source failed.

The process exits 1 if all sources failed or email delivery failed; partial success exits 0 with explicit warnings and a PARTIAL email subject. No report artifacts or listings are committed or uploaded by workflows. Plain text and HTML exist in memory only. Provider response bodies, credentials, recipient addresses and property descriptions are not logged.

## Access conditions

`robots.txt` is fetched before search/details and checked for every URL. Missing/unreadable robots data fails closed. Crawl-delay is honored when supplied. Cross-host URLs and redirects are refused for manual review. HTTP 401, 403 or 429 and recognized access challenges stop that source immediately. The application never bypasses CAPTCHA, login, anti-bot controls or restrictions, and does not retry restricted responses with alternate identities.

At inspection Storia robots permitted the search and detail paths used. Its footer linked legal information on `help.storia.ro`; the help pages returned a JavaScript application shell, so substantive current terms could not be verified from their HTTP responses. **Robots permission is not a determination that site terms permit your use.** Review current site terms and obtain permission where required before scheduling production use; disable a source in config if its conditions prohibit automated access. No access restriction was bypassed in inspection. Imobiliare’s public terms page was retrieved and reviewed for automated-access clauses; the explicit scraping restriction observed applies to ImoAI responses, which this application never accesses. Public listing HTML is used, subject to robots and runtime access restrictions. Initial 403 responses and subsequent successful access are recorded in validation. No gated contact data, login-only publication history, or AI interfaces are requested.

## Resend setup

1. Create a Resend account and add a domain you control under Domains.
2. Add the DNS verification records Resend provides and wait until verified.
3. Create a sending API key; restrict scope/domain where the provider supports it.
4. Choose `REPORT_EMAIL_FROM` under that verified domain and set your recipient as `REPORT_EMAIL_TO`. Provider sandbox accounts may permit only a verified recipient.
5. Store the key and addresses as GitHub repository Secrets. Do not place them in config.yaml.
6. A successful API response means Resend accepted the message; inspect its dashboard for delivery/bounce status.

Delivery uses one HTTPS API request with an idempotency key. There is no automatic resend after ambiguous timeouts, avoiding repeated emails from uncertain acknowledgements. A rejected request or timeout fails the workflow. Resolve delivery in the provider dashboard before manually rerunning.

## Exact GitHub configuration

1. Create a **private** repository on GitHub. Initialize it with the contents of this directory, including hidden `.github` files. Do not upload `.venv`, `.env`, caches, or any live scrape files. The ZIP contains only project files and synthetic fixtures.
2. Commit and push to the default branch. Scheduled workflows run from the default branch.
3. Open **Settings → Actions → General**. Enable Actions and allow the pinned GitHub checkout/setup-python actions. Keep workflow token permissions read-only; these workflows request only `contents: read`.
4. Open **Settings → Secrets and variables → Actions → New repository secret** and create exactly `RESEND_API_KEY`, `REPORT_EMAIL_TO`, and `REPORT_EMAIL_FROM`.
5. Open **Actions → Tests**, inspect a successful test run. Tests use mocked HTTP, no credentials.
6. Review the source access terms and `config.yaml` coverage limits. Both sources are enabled; disable either source if its current access conditions prohibit your intended use.
7. Open **Actions → Daily apartment scan → Run workflow**, select the default branch and click **Run workflow**. This manual run scans and sends one report immediately, independent of the time gate.
8. Inspect **Actions → run → scan → Scan and email** for per-source status/counts and coverage warnings. Check the Resend dashboard and inbox.
9. Leave the workflow enabled for daily operation. Your computer can be off. Private repositories use your GitHub Actions allocation/billing; check your account's minute budget and Resend email limits.

The workflow has two UTC schedules, 05:00 and 06:00. A Europe/Bucharest offset gate selects 05:00 UTC during UTC+3 summer time and 06:00 UTC during UTC+2 winter time, giving one daily scan at the intended local 08:00. This is a DST-safe fallback that does not require a timezone scheduling extension. The unused scheduled run exits after a short gate step, before checkout/install. It uses the schedule expression, so ordinary runner delays past the scheduled hour do not skip the selected scan. GitHub schedules are best effort and may be delayed or dropped; exact 08:00 execution is not guaranteed. Manual reruns intentionally send additional reports.

Ubuntu GitHub-hosted runners, Python 3.12, hash-locked dependencies, 45-minute timeout, a shared concurrency group and `cancel-in-progress: false` prevent overlapping scans. One pending run may be replaced by GitHub's concurrency semantics. No Playwright/browser installation is required. Action revisions are pinned by commit SHA.

## Configuration and maintenance

Edit `filters` for rooms, construction year, strict price ceiling and exact polygon. Keep city/transaction/property type consistent with the adapter's Bucharest sale-apartment search URL. Changing those values alone does not change the search URL. Edit `websites` to disable a source; at least one must remain enabled. Edit `http` for request timeout, rate and caps; edit `email.subject` and logging level for nonsecret presentation. Never add secrets to YAML.

Dependencies use well-established HTTPX, Beautiful Soup, PyYAML (safe_load) and Shapely packages; no third-party scraper repositories are used. Versions and transitive dependencies are hash-locked. The small local robots matcher handles wildcard and end-anchor rules, most-specific user-agent groups, Allow ties and crawl delay; tests cover these decisions. Tests include a pip-audit known-vulnerability check. This is an advisory database check, not a guarantee against unknown vulnerabilities. Review release notes and regenerate both lockfiles when upgrading:

```bash
uv pip compile pyproject.toml --generate-hashes -o requirements.lock
uv pip compile pyproject.toml --extra dev --generate-hashes -o requirements-dev.lock
python -m pip_audit -r requirements.lock --disable-pip
```

Use an explicitly writable `--cache-dir` when auditing in a restricted environment. `uv` is only a maintenance tool; Actions installs directly from lockfiles with pip. Python package build metadata is provided for normal packaging, but the supported locked execution path uses `PYTHONPATH=src` and does not invoke a build backend.

## Troubleshooting

- **403/429, CAPTCHA or robots denial:** stop that source, review site policy or contact the operator. Do not add proxies or CAPTCHA solvers. Re-run the controlled smoke test after permission/access changes.
- **Missing payload/schema or pagination warnings:** site structure may have changed. Inspect a small permitted page, update the corresponding adapter, create a sanitized synthetic fixture following the new schema and rerun tests. Never treat parser failure as a successful empty scan.
- **Few or no matches:** inspect coverage caps, year availability, strict price rule, room count and location precision. Missing usable area affects sorting, not eligibility. Non-EUR prices and missing years cannot qualify. Unverified pins appear separately. Default city coverage is capped.
- **Imobiliare fails or stops pagination:** access has varied between 403 and 200. A 403 stops the scan immediately. Robots currently restrict query pagination beyond page 10; this creates partial coverage even when detail parsing works. Do not evade those restrictions.
- **Email missing:** check all three Secrets, verified sender/domain and recipient restrictions; inspect provider dashboard. Delivery failure exits 1. Do not log provider bodies or keys for diagnosis.
- **No scheduled run:** confirm the workflow is on the default branch, enabled, has available runner minutes and Actions permissions. GitHub cron can be delayed. One of the two daily scheduled jobs intentionally skips the scan.

## Layout and validation

`src/apartment_scraper/` contains independent adapters, rate-limited robots-aware HTTP, config, data models, filtering, duplicate handling, reporting, delivery and CLI. `.github/workflows/` holds scheduled and test jobs. `tests/fixtures/` contains **synthetic minimal HTML**, modeled on inspected structures; no actual listings, user/session tokens or scraped reports are included. `requirements*.lock` pin runtime/test dependencies with hashes.

See `VALIDATION.md` for executed tests, live observations and untested integration boundaries. No GitHub repository was created or workflow activated, and no live email was sent as part of building this project.
