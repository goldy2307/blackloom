# On-Chain ETL & Analytics Pipeline

Beginner-friendly ETL pipeline. Mock blockchain data (or real Etherscan API) → clean → SQLite → Power BI.

## Prerequisites

1. Python 3.10+ installed (`python --version` to check)
2. pip (comes with Python)
3. (Optional, only for real data) free Etherscan API key: https://etherscan.io/apis
4. Power BI Desktop (Windows) or Power BI service, for final dashboard step
5. Optional: "DB Browser for SQLite" app, to visually inspect the `.db` file

## Setup

```bash
cd onchain-etl
pip install -r requirements.txt
cp .env.example .env
```

Leave `DATA_SOURCE=mock` in `.env` for first run — no API key needed.

## Run

```bash
cd src
python main.py
```

Output files land in `data/processed/`:
- `transactions_clean.csv` — cleaned tx-level data
- `onchain.db` — SQLite database (indexed, queryable)
- `daily_summary_for_powerbi.csv` — aggregated daily stats, ready for Power BI

## Flow — what actually happens

```
extract.py          transform.py                 load.py
   |                     |                          |
raw JSON  --------> pandas DataFrame --------> SQLite + CSV export
(API/mock)          (validate, clean,          (indexed table +
                     dedupe, cast types)         daily_summary view)
```

**1. Extract** (`extract.py`)
Pulls raw transaction records — either from Etherscan's real API or a generator that fakes realistic tx data (hash, from, to, value in wei, gas, timestamp). Saves untouched as JSON. Extract never cleans anything — keep raw stage "dumb" so you always have an unmodified copy to debug against.

**2. Transform** (`transform.py`)
This is the core engineering work:
- **Schema validation**: checks every row has the required fields (hash, from, to, etc). Rows missing fields get dropped. `integrity % = valid_rows / total_rows` — this is literally where a "99.9% data integrity" metric comes from.
- **Type casting**: blockchain values arrive in wei (1 ETH = 10^18 wei) and unix timestamps — converted to human units (ETH, gwei, datetime).
- **Deduplication**: `drop_duplicates(subset="hash")` — tx hash is unique per real transaction, so duplicate hashes = data pulled twice (common with paginated APIs).

**3. Load** (`load.py`)
Writes clean data into SQLite using `sql/schema.sql`, which defines:
- A `transactions` table with `hash` as PRIMARY KEY (blocks accidental duplicate inserts)
- Indexes on `from_address`, `to_address`, `tx_time`, `block_number` — without these, every filtered query (e.g. "all tx from wallet X") scans the whole table row by row. Indexes let SQLite jump straight to matching rows. This is the mechanism behind a "30% query latency reduction" claim.
- A `daily_summary` VIEW that pre-aggregates tx count, ETH volume, avg gas price, failed-tx count per day — this is the query Power BI actually reads.

**4. Power BI**
Open Power BI Desktop → Get Data → Text/CSV → point at `daily_summary_for_powerbi.csv` → build charts (line chart for daily volume, bar for tx count, card for failed tx). Set it to auto-refresh on a schedule → that's your "automated weekly reporting" piece.

## Production hardening (new)

This is the "real product" layer: data science depth, security, monitoring, and CI, on top of the automated pipeline.

### 1. Data science layer (`src/analytics.py`, `src/quality.py`)
- **Anomaly detection**: z-score on transaction value and gas price. |z| > 3 = statistical outlier, flagged with the actual score, not just "high/low."
- **Trend analysis**: 7-day rolling mean/std on daily ETH volume — smooths day-to-day noise so you can see real direction.
- **Forecasting**: least-squares linear regression (`numpy.polyfit`) on the trailing 14 days, predicts next 3 days. Deliberately simple and transparent — a defensible baseline, not a black box.
- **Data quality score**: real multi-dimension scoring (completeness, uniqueness, validity, timeliness), each independently computed and weighted — this is how actual data platforms (Great Expectations, Monte Carlo) score pipelines, not a single vague "integrity %."

Exposed via `/api/analytics` and `/api/quality`, rendered on the dashboard.

### 2. Security
- `POST /api/run-pipeline` requires an `X-API-Key` header if `API_KEY` is set in `.env`. Empty = auth disabled (local dev only — **always set a real key before deploying publicly**).
- Rate limiting: 5 requests/minute on the trigger endpoint (`slowapi`), stops accidental or malicious hammering of a real workload.
- CORS restricted via `ALLOWED_ORIGINS` env var (comma-separated) instead of `*` in production.
- Docker container runs as non-root user.

### 3. Monitoring
- `/metrics` — Prometheus-format metrics (request counts, latencies). Point a Prometheus server + Grafana at it for real dashboards on the API itself, separate from the business dashboard.
- `/api/health` — for uptime checks / load balancer health probes / Docker's own `HEALTHCHECK`.
- `logs/pipeline.log` — structured, timestamped, persists via Docker volume.

### 4. Testing & CI
- `tests/` — pytest unit tests on the actual logic (schema validation, dedup, quality scoring math). Run: `pytest tests/ -v`
- `.github/workflows/ci.yml` — on every push/PR: installs deps, runs tests, runs a full pipeline smoke test, builds the Docker image. Fails the build if any of that breaks.

### 5. Deploying it live — what I can hand you vs. what needs your own account

I can write and test every line of code above, and did — ran the tests, ran the pipeline, hit every endpoint, confirmed auth returns 401/200 correctly and rate limiting fires at request 5. What I *can't* do is create a cloud account or push to a live public URL on your behalf — that needs your credentials. Here's the actual path, honestly:

**Cheapest real path (Render, free/low-cost tier):**
1. Push this project to a GitHub repo (`git init`, commit, push)
2. Render.com → New → Web Service → connect the repo
3. Render detects the `Dockerfile` automatically → set build command none needed, it just builds the image
4. Add environment variables in Render's dashboard: `API_KEY`, `PIPELINE_INTERVAL_MINUTES`, `ALLOWED_ORIGINS` (your Render URL)
5. Attach a persistent disk mounted at `/app/data` (Render supports this) — without it, your SQLite DB resets every deploy
6. Deploy → you get a public HTTPS URL, dashboard live, pipeline running itself on schedule

**Alternative**: Railway.app or Fly.io — near-identical flow, also read your `Dockerfile` directly.

**If you specifically need Postgres instead of SQLite** (for real concurrent multi-user load): Render/Railway both offer a managed Postgres add-on. That requires a small code change in `load.py` (swap `sqlite3` for `sqlalchemy` + the Postgres connection string) — say the word and I'll make that change, it's a contained edit.

### Scaling beyond one instance
The scheduler runs in-process, so running 2+ replicas of this container would duplicate every pipeline run. For real horizontal scaling: split into two services — a scheduler/worker service (runs `src/main.py` on a cron) and a stateless API service (just serves reads, scale freely). I kept it as one service here because it matches the project's actual scale — flag it if you outgrow this.

## Going further (optional, once comfortable)

- Switch `.env` to `DATA_SOURCE=real` + add your Etherscan key + a wallet address → pulls actual on-chain data instead of mock.
- Swap SQLite for Postgres if you want a "real" multi-user DB (schema.sql is 95% portable, minor syntax tweaks).
- Add a `scheduler.py` using `schedule` lib or cron to re-run `main.py` weekly — that's the "automation" piece for the resume line.