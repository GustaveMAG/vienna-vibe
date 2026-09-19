# Vienna Vibe

An hourly data pipeline that pairs weather data with my own Spotify listening
history, so I can ask whether the weather actually changes what I listen to.

I started this in Vienna during an exchange semester. The first version was a
desktop app that generated playlists on the fly. It still lives on the
[`v1-flet-app`](../../tree/v1-flet-app) branch, but it stopped being viable
when Spotify restricted the audio-features and recommendations endpoints in
November 2024, so I rebuilt it as a pipeline that collects and stores the data
instead of throwing it away.

## How it works

```mermaid
flowchart LR
    OM["Open-Meteo"] --> W["ingest_weather"]
    SP["Spotify<br/>recently-played"] --> L["ingest_listening"]
    W --> RAW[("raw<br/>JSONB payloads")]
    L --> RAW
    W --> FW[("core.fact_weather_hourly")]
    L --> FL[("core.fact_listening_event")]
    FW --> Q{{"quality checks"}}
    FL --> Q
    Q --> M[("marts<br/>analysis views")]
```

Three steps run every hour: fetch the weather for each tracked location, fetch
recent plays, then run the quality checks against the consolidated state. If a
check fails the run fails, because a dashboard that is quietly wrong is worse
than one that is obviously broken.

## Two constraints that shaped the design

**Spotify only returns the last 50 plays.** Anything older is gone for good,
there is no backfill endpoint. That is why collection runs hourly rather than
daily, and why each run deliberately asks for the previous three hours as well.
If a run fails, the next one picks up what it missed.

**That overlap means every run sees data it has already stored.** Each fact
table has a unique natural key and every write goes through
`INSERT ... ON CONFLICT`, so re-running an hour leaves the database exactly as
it was:

| table | natural key | on conflict |
|---|---|---|
| `fact_weather_hourly` | `(location_id, observed_at)` | update, since Open-Meteo revises recent values |
| `fact_listening_event` | `(played_at, track_id)` | do nothing, a play is immutable |
| `dim_track` | `track_id` | update, popularity drifts over time |

The pipeline takes the hour it is processing as an argument rather than reading
the clock, which is what makes replays reproducible. `test_integration_idempotence.py`
loads the same fixture twice and asserts the row counts match.

## Data model

Three schemas. `raw` keeps every API payload as JSONB so I can replay
transformations without re-querying APIs that have short history windows.
`core` holds the dimensional model: four dimensions, two fact tables, and a
`pipeline_run` log. `marts` is seven views, recomputed on read.

The one I actually care about is `marts.v_listening_by_weather_family`:

```sql
SELECT weather_family, plays, distinct_artists, avg_popularity
FROM marts.v_listening_by_weather_family
ORDER BY plays DESC;
```

`pipeline_run` records rows read, written and skipped per step. The skipped
count is the useful one: it measures how much the runs overlap. If it drops to
zero the schedule is too sparse and plays are being lost.

## Running it

Locally, with Docker:

```bash
cp .env.example .env    # fill in the Spotify credentials
docker compose up -d
```

That brings up Postgres and Airflow, applies the schema, and enables the
`vienna_vibe_hourly` DAG. Airflow is at http://localhost:8080.

Without Docker:

```bash
pip install -e ".[dev]"
export DATABASE_URL=postgresql://vienna:vienna@localhost:5432/vienna_vibe
vienna-vibe migrate
vienna-vibe run
vienna-vibe stats
```

To replay a past hour: `vienna-vibe run --window 2026-09-19T14:00:00Z`.

### Spotify credentials

Create an app in the [developer dashboard](https://developer.spotify.com/dashboard)
with `http://127.0.0.1:8888/callback` as a redirect URI, then authorise the
`user-read-recently-played` scope:

```
https://accounts.spotify.com/authorize?client_id=CLIENT_ID&response_type=code&redirect_uri=http://127.0.0.1:8888/callback&scope=user-read-recently-played
```

Exchange the `code` you get back for a refresh token:

```bash
curl -X POST https://accounts.spotify.com/api/token \
  -u "CLIENT_ID:CLIENT_SECRET" \
  -d grant_type=authorization_code \
  -d code=THE_CODE \
  -d redirect_uri=http://127.0.0.1:8888/callback
```

The refresh token does not expire. It goes in `.env`, which is gitignored.

## On Azure

The pipeline runs about a minute an hour, so a VM sitting idle the rest of the
time made no sense. `infra/azure/deploy.ps1` provisions a Container Apps Job on
an hourly cron, a PostgreSQL Flexible Server, Key Vault for the four secrets,
and a Container Registry. The script checks for each resource before creating
it, so it doubles as the deployment path for a new image.

```powershell
cd infra/azure
./deploy.ps1 -SpotifyClientId "..." -SpotifyClientSecret "..." -SpotifyRefreshToken "..."
```

`teardown.ps1` deletes the resource group and purges the vault. See
[`infra/azure/README.md`](infra/azure/README.md) for the operational commands.

Airflow stays in the repo for local development. In production Azure handles
the scheduling.

## Tests

```bash
make test
make lint
```

The unit tests cover the transformation logic with no network or database:
pivoting Open-Meteo's parallel arrays into rows, guarding against arrays of
unequal length (which would silently shift every reading by one hour),
deduplicating overlapping Spotify pages, and surviving malformed payloads.

The integration tests need `DATABASE_URL` and skip without it. They check
idempotence, natural keys, and that all seven views compile, which unit tests
cannot see.

CI runs both, plus it replays the migrations to confirm they are re-runnable.

## Known limitations

The Postgres firewall is open to Azure services rather than sitting behind a
VNet with a private endpoint, and the job authenticates with a password rather
than a managed identity. Both are deliberate trade-offs for a personal project
with no third-party data on it, and both are the first things I would change if
this held anything sensitive.

Weather is joined to plays on the truncated hour. That is coarse: a play at
14:59 gets the 14:00 observation. Fine for the question I am asking, wrong if
you wanted minute-level correlation.

`ruff` is pinned to an exact version. Formatters change their output between
releases, and an open bound means CI breaks on code nobody touched.
