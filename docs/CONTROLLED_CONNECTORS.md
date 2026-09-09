# Controlled Connectors

## Scope

CrisisAgent supports controlled ingestion, not unrestricted internet crawling. Supported connector types are allowlisted RSS feeds, single `article_url` sources, and manually enabled GDELT DOC / NewsAPI query connectors, plus local JSON/CSV fixtures for offline testing.

## Rules

- Sources are registered before use and default to `enabled=false`.
- URLs must use HTTPS and be one of the supported connector types.
- Live collection requires an explicit server switch and manual user confirmation.
- Connectors respect `robots.txt`, timeout, rate limits, and source-level `max_items`.
- The system does not recurse through links, bypass login/CAPTCHA, use proxy pools, or collect private/authorized-only content.
- `no_match`, `failed`, `skipped_by_robots`, and `disabled` are distinct outcomes; a failed source is not treated as "no opinion".

## Data Handling

Collected records retain source identity and timestamps before normalization, deduplication, clustering, and risk analysis. Unverified, conflicting, uncertain, or high-risk clusters are preserved as structured signals for Human Review rather than treated as verified facts.

## Boundary

The controlled connector is an MVP validation path. It is not a real-time, whole-web enterprise monitoring platform and it never automatically publishes a response.
