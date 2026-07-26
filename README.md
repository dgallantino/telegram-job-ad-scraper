# telegram-job-ad-scrapper

A bot that listens to one Telegram group, detects job-ad links from a
supported allowlist of sites, crawls them, and writes structured results
into a Google Sheet ("Sheet A"). A separate, human-facing "Sheet B" pulls
from Sheet A but is entirely out of scope for this project.

## Tech stack

- **Crawling:** `httpx` (async) + `beautifulsoup4` + `lxml` as the parser backend.
- **Google Sheets:** `gspread` with `google-auth` for service-account auth.
  No hand-rolled raw HTTP calls to the Sheets API.
- **Telegram:** `python-telegram-bot`, but only its low-level `Bot` class
  (`bot.get_updates()`, `bot.send_message()`, etc.) — explicitly **not** the
  `Application`/`ApplicationBuilder` polling/handler framework. The project
  drives its own asyncio loop and its own offset/state persistence; PTB is
  used purely for typed API calls and its built-in flood-control retry
  handling.

## Project structure

```
telegram-job-ad-scrapper/
├── src/
│   └── job_scraper/
│       ├── main.py            # entrypoint: wires everything, runs the event loop
│       ├── config.py          # env var loading / settings
│       ├── state.py           # local JSON state file read/write
│       ├── telegram_bot.py    # listener: get_updates, validate, reply, enqueue
│       ├── queue.py           # asyncio.Queue wiring + worker loop
│       ├── sheets.py          # Sheet A read/write client (gspread)
│       └── scraper/
│           ├── dispatch.py    # site allowlist -> parser lookup
│           ├── fetch.py       # async httpx fetch of a single URL
│           └── sites/
│               ├── models.py          # JobFields shared type
│               ├── registry.py        # *_site discovery / allowlist
│               ├── jobstreet_site.py  # id.jobstreet.com parser
│               └── threads_site.py    # threads.com / threads.net parser
├── pyproject.toml
├── Containerfile
├── README.md
└── .env.example
```

## Architecture

### Telegram access

- Bot API only (not MTProto/user-account). The bot must be added to the one
  target group.
- Long polling via `getUpdates`. Offset tracking = Telegram's `update_id`.

### Process model

- Single process, asyncio-based. One task is the Telegram listener
  (validates + replies + enqueues). One or more worker tasks are the
  scraper, consuming an in-memory `asyncio.Queue`. Runs as a single Podman
  container.
- Crash recovery: on startup, the process scans Sheet A for rows with
  `crawl_status` in (`pending`, `running`) and re-enqueues them before
  starting the listener.

### State persistence

- A local JSON file on a mounted volume (`/data/state.json` by default)
  stores at minimum the last processed `update_id`. It is written after each
  processed batch of updates, not per message.

### Reconciliation logic (priority order)

1. Resume from `update_id` in the local state file, if present and valid.
2. If absent/corrupt: attempt to derive a resume point from Sheet A
   (`job_id`, `timestamp` columns) — best-effort only, see the limitation
   below.
3. If both fail: ignore backlog, accept only new incoming updates from that
   point forward.

### Google Sheets — Sheet A columns

`job_id` (string `{chat_id}_{message_id}`), `timestamp`, `url`, `crawl_status`
(`pending`/`running`/`finished`/`failed`/`rejected`), `job_title`,
`job_description`, `job_location`, `job_company`, `job_salary`, `job_type`,
`job_posted_date`.

- Rejected/unsupported URLs still get a row with `crawl_status = rejected`,
  for audit — they are never silently dropped after replying in chat.
- Writes are batched/minimized — the Sheets API has real rate limits; the
  design deliberately avoids per-message synchronous writes.

### Main flow

1. Incoming group message → listener validates the URL (well-formed + site
   is in the supported allowlist).
2. Quick reply in chat: accepted or rejected (and why, briefly).
3. If accepted: write a `pending` row to Sheet A, enqueue for crawling.
4. A worker picks up the job, sets `running`, crawls (no link-following,
   single given URL only), writes result fields plus `finished`/`failed` to
   Sheet A.
5. On finish, the worker sends a message back to the group with the result
   summary.

### Constraints

- No external infra dependency (no self-hosted DB, no Redis). Google Sheets
  is the only external service, used deliberately as the data store.
- Only one Telegram group is ever listened to.
- The scraper only supports an explicit, small allowlist of sites.
- The scraper never follows links found on a page; it only parses the given
  URL.

## Configuration

Copy `.env.example` to `.env` and fill in real values:

| Variable | Required | Description |
| --- | --- | --- |
| `GOOGLE_SERVICE_ACCOUNT_KEY` | yes | Path to the Google service-account JSON key file. |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | yes | Spreadsheet ID containing Sheet A. |
| `GOOGLE_SHEETS_SHEET_NAME` | yes | Worksheet/tab name for Sheet A. |
| `TELEGRAM_BOT_TOKEN` | yes | Bot API token. |
| `TELEGRAM_CHAT_ID` | yes | The one target group's chat ID. |
| `STATE_FILE_PATH` | no (default `/data/state.json`) | Path to the local JSON state file. |
| `WORKER_COUNT` | no (default `1`) | Number of scraper worker tasks. |
| `TELEGRAM_POLL_TIMEOUT` | no (default `30`) | `getUpdates` long-poll timeout, in seconds. |

Never commit `.env` or the service-account JSON key — both are gitignored.

## Running locally with Podman

Build the image:

```bash
podman build -t job-scraper -f Containerfile .
```

Run it, mounting the state directory and injecting secrets via env vars
(this is the compose-equivalent for a single-container app):

```bash
podman run -d \
  --name job-scraper \
  -v job-scraper-data:/data \
  -v /path/to/service-account.json:/secrets/service-account.json:ro \
  -e GOOGLE_SERVICE_ACCOUNT_KEY=/secrets/service-account.json \
  -e GOOGLE_SHEETS_SPREADSHEET_ID=... \
  -e GOOGLE_SHEETS_SHEET_NAME=Sheet1 \
  -e TELEGRAM_BOT_TOKEN=... \
  -e TELEGRAM_CHAT_ID=... \
  job-scraper
```

## Known limitations

- `getUpdates` only returns unacknowledged updates; Telegram buffers roughly
  the last 24 hours of them. It cannot fetch arbitrary chat history. If the
  local state file is lost and more than that buffer window has elapsed,
  messages sent during the gap are unrecoverable through this API —
  reconciliation can only prevent *reprocessing* of updates Telegram still
  has buffered, not recover ones it has already dropped.

## Not yet implemented

This is a scaffold. The following are real, working code:

- `config.py` — env var loading, validation, and defaults.
- `state.py` — JSON state-file read/write.
- `scraper/dispatch.py` — URL well-formedness check and site-allowlist
  lookup mechanism.
- `scraper/sites/jobstreet_site.py` — `id.jobstreet.com` job-detail parser.
- `scraper/sites/threads_site.py` — Threads post parser.
- `queue.py` — `asyncio.Queue` creation and worker-pool spawn/shutdown
  plumbing.

The following are stubs (correct signatures, `TODO`s, `NotImplementedError`
bodies) with no real behavior yet:

- `sheets.py` — `SheetsClient` is not yet authenticated/connected; no reads
  or writes happen.
- `telegram_bot.py` — `Bot` construction is real, but `run_listener` does
  not yet poll, validate, reply, or enqueue anything.
- `queue.py`'s `process_job` — does not yet crawl, parse, or write results.
- `main.py`'s Sheet-A re-enqueue-on-startup step and the listener startup
  call are both `TODO`.
