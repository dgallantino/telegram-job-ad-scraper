# Roadmap

Living wishlist of product improvements for `telegram-job-ad-scrapper`. Items stay within project constraints: one Telegram group, Google Sheets as the only datastore (no DB/Redis), allowlist-only crawling of a single given URL, and no work on downstream / human-facing sheets.

This document is big-picture only — what and why, not how to implement.

---

## Recovery

### State reconciliation from `jobs`

When the local state file is missing or corrupt, resume Telegram processing using a best-effort signal from the `jobs` worksheet (for example prior `job_id` / `timestamp` rows). This is the second step in the project’s reconciliation priority order, after a valid local `update_id`.

**Caution:** Telegram only buffers unacknowledged updates for roughly 24 hours. Reconciliation can avoid reprocessing what is still buffered; it cannot recover messages Telegram has already dropped.

### Crawl retries

Allow failed crawls to be tried again — automatically with limits and/or on demand — so transient network or site errors do not permanently strand a row in `failed`.

**Caution:** Retries must be bounded. Unbounded or aggressive retry loops can hammer allowlisted sites and burn through Sheets API quota.

---

## Sheet audit fields

### Failure reason column

Persist a short explanation when a crawl ends as `failed` (HTTP error, parse failure, timeout, and similar) so operators can diagnose problems from the sheet without digging through container logs.

### Reject reason column

Persist why a URL was rejected (invalid URL, unsupported site, and similar). Today the listener already communicates a reason in chat, but that reason is not written to `jobs`.

**Caution:** Both of these expand the `jobs` worksheet schema. Any new columns become part of the sheet contract and must stay consistent with header expectations on connect.

---

## Telegram UX

### Richer finish replies

When a crawl finishes or fails, reply in the group with a useful summary — for example job title and company on success, or a brief failure cause on error — instead of a generic finished/failed stub.

Keep replies short; the sheet remains the source of truth for full fields.

---

## Scraper

### More allowlisted site parsers

Grow the supported set by adding more site-specific parsers, each registered through the existing allowlist / site-module pattern. Scope stays an explicit small allowlist — never arbitrary hosts.

**Caution:** Scrape only the submitted URL. Do not follow links found on the page. Prefer sites the group actually posts.

### URL dedupe

Before accepting a new job, check whether the same URL already exists in `jobs` (especially `pending`, `running`, or `finished`). Avoid duplicate crawls and duplicate rows when the same link is posted again.

**Caution:** Deduping against Sheets implies extra reads; design so it does not multiply API calls under bursty chat traffic.

### Fetch politeness

Throttle how aggressively workers fetch pages — for example concurrency caps or delays between requests — so higher `WORKER_COUNT` does not overload target sites or trip blocks.

Stay within the allowlist and single-URL fetch model.

---

## Sheets throughput

### Write batching

Coalesce or batch worksheet writes where practical so accept / status / result updates do not issue a Sheets API call per tiny mutation under load.

**Caution:** Sheets rate limits are real. Batching must remain in-process only — do not introduce a second datastore or write queue outside the existing memory + Sheets model.

---

## LLM

### Non-blocking LLM calls

Where optional LLM field extraction is used (for example Threads fallback), ensure those calls do not stall the asyncio event loop so other workers and the Telegram listener stay responsive.

**Caution:** LLM extraction remains non-critical and fail-silent: regex / deterministic parse results must still win if the LLM is slow, misconfigured, or unavailable.
