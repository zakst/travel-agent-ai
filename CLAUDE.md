# CLAUDE.md — travel-agent-ai

Project memory for future Claude Code sessions on this repo.

## Project overview

`travel-agent-ai` is a Python AI agent that researches flights and hotels
using **real APIs** (Duffel + Open-Meteo) and writes a markdown trip report.
It is research-only — **it never books anything**. The "agent" is the
Anthropic Messages API tool-use loop in `agent.py`.

## Architecture

The classic Anthropic agent loop:

- **Tool schemas** in `tools.py::TOOL_SCHEMAS` are the only thing Claude
  sees. They drive its tool calls.
- **Implementations** in `tools.py` are normal Python functions that hit
  real APIs (`search_flights`, `search_hotels`, `get_weather_forecast`,
  `save_report`).
- **Dispatcher** `tools.py::execute_tool` translates Claude's tool calls
  back into Python function calls and JSON-encodes the result.
- **Agent loop** `agent.py::run_agent` runs `messages.create` → handle
  tool_use blocks → append tool_result → repeat until `end_turn`.

`duffel_client.py` exists so `tools.py` can stay focused on schema-and-parse
logic instead of HTTP plumbing. `geocoding.py` is its own module because
both `search_hotels` and `get_weather_forecast` need to convert city names
to lat/lon.

## Key files & where to make changes

| Want to...                                | Touch                                                                                  |
| ----------------------------------------- | -------------------------------------------------------------------------------------- |
| Add a new tool                            | `tools.py`: add to `TOOL_SCHEMAS`, write the impl, add a dispatcher entry. Add a test. |
| Change agent behavior / persona / format  | `SYSTEM_PROMPT` in `agent.py`                                                          |
| Change the model                          | `DEFAULT_MODEL` in `agent.py`                                                          |
| Switch flight/hotel provider              | Replace `search_flights`/`search_hotels` impls; rewrite `duffel_client.py` for the new auth pattern. **Schemas stay the same.** |
| Switch test → live Duffel                 | Swap `duffel_test_*` for a live token and apply for production access in the Duffel dashboard. |
| Tweak report sections                     | The list in `SYSTEM_PROMPT`                                                            |

## Conventions

- Type hints required on every function signature.
- `from __future__ import annotations` at the top of every module.
- Tool functions catch their own exceptions where it matters; the
  dispatcher (`execute_tool`) is the safety net — it converts every
  exception into a JSON `{"error": ...}` blob so the agent loop never
  sees a raw exception.
- `DuffelClient` is a module-level singleton in `tools.py`, accessible
  via `_get_duffel_client()`. Tests can monkeypatch the singleton.
- `save_report` writes to `./reports/` (gitignored). Filenames are
  sanitised with `Path(filename).name`.
- No code comments unless behaviour is non-obvious — rely on names and
  docstrings. Add a brief comment only when there's an exception, edge
  case, or external API quirk that would surprise a reader.
- Module-level constants are `UPPER_CASE`.
- No `print` statements outside `agent.py`'s verbose logging and
  `main.py`'s output.

## Testing

- All HTTP is mocked with **respx** in unit tests. The `respx_mock`
  fixture defaults to `assert_all_called=True` and `assert_all_mocked=True`,
  so an unexpected outbound HTTP call fails the test loudly.
- The Anthropic client is **injectable** into `run_agent(client=...)` so
  tests pass a `MagicMock` instead of hitting the real API.
- Module-level singletons (`_duffel_client`, `_weather_client`,
  `geocoding._client`) are reset between tests by an autouse fixture in
  `tests/conftest.py`.
- Integration tests live in `tests/test_integration.py` and are marked
  `@pytest.mark.integration`. They skip themselves when
  `DUFFEL_ACCESS_TOKEN` is missing. Open-Meteo tests always run because
  the API needs no key.

Commands:

```bash
pytest                 # unit tests (default — no network)
pytest -m integration  # live-API tests (require real credentials)
pytest tests/test_tools.py::test_search_flights_parses_duffel_offers
```

CI runs `.github/workflows/tests.yml` on every push to `main` and every
PR targeting `main`, across Python 3.10/3.11/3.12. No secrets needed —
the unit suite is fully respx-mocked. Integration tests are intentionally
not part of CI; gate them on `workflow_dispatch` if you ever want them.

When adding a new tool, write at minimum:
- A parse-success test
- A parse-empty-input test
- An error-handling test (Duffel error or invalid input)

## Common tasks

```bash
# Install
pip install -r requirements.txt

# Run with the default Tokyo request
python main.py

# Run with a custom request
python main.py "A 4-day Lisbon trip from JFK, May 8-12 2026, hotel under $200"

# Run unit tests
pytest

# Run all (incl. live) tests
pytest -m integration

# Quick sanity-check a single tool
python -c "from dotenv import load_dotenv; load_dotenv(); \
import tools; print(tools.get_weather_forecast('Tokyo', '2026-06-15', '2026-06-21'))"
```

## API gotchas

- **Duffel POST bodies must be wrapped in `{"data": {...}}`** — the
  `DuffelClient.post` wrapper handles this; callers pass only the inner
  dict.
- **Duffel requires `Duffel-Version: v2`** on every request — wrapper
  sends this automatically.
- **Duffel test mode** only returns realistic data from the sandbox airline
  "Duffel Airways" (IATA `ZZ`). Real airlines may appear but with synthetic
  prices — never present them as real-world quotes.
- **Duffel Stays needs separate dashboard access approval.** Flights work
  immediately; hotels do not until you click the access request.
- **Stays search is by lat/lon + radius (km), max 100 km.** That's why
  we geocode the city name first, via Open-Meteo.
- **Durations come as ISO 8601 (`PT11H30M`)** and need parsing. For
  round-trips, sum the durations across both slices.
- **Open-Meteo's `/forecast` rejects dates >~16 days ahead with a 400.**
  `get_weather_forecast` detects this via `_today()` and routes far-out
  dates to `_historical_climatology`, which samples the archive API for
  the same calendar dates across the last 3 years and averages them.
  Climatology results are tagged `"source": "historical_climatology"` so
  the agent can frame them as "typical" rather than "the forecast says".
- **Tests pin the clock with the `fix_today` fixture** (set to
  2026-06-12) so the existing weather-forecast tests deterministically
  hit the live-forecast branch. The new climatology test monkeypatches
  `tools._today` directly to push the trip dates outside the forecast
  window.
- **Open-Meteo geocoding returns `{}` for unknown cities** (no `results`
  key at all) — don't crash on missing keys.

## Going to production checklist

- Apply for live Duffel access; swap the test token for a production token.
- Add real rate-limit handling (Duffel surfaces these) and exponential
  backoff in `duffel_client.py`.
- Add an in-memory cache for the same query within a session.
- Consider Anthropic prompt caching on `SYSTEM_PROMPT` and `TOOL_SCHEMAS`
  (they're stable across requests).
- Add structured logging with request IDs.
- Lock down cabin class / passenger configurations more strictly at the
  schema level.

## Models

Three-tier strategy (override `DEFAULT_MODEL` or pass `model=` to
`run_agent`):

- **Haiku** (`claude-haiku-4-5-20251001`) for dev iteration.
- **Sonnet** (`claude-sonnet-4-6`) — production default.
- **Opus** (`claude-opus-4-7`) for the hardest reasoning cases.

## What NOT to do

- **Don't add real booking actions** without an explicit
  human-in-the-loop confirmation step.
- **Don't pass user input directly into shell or filesystem operations.**
  `save_report` strips path components for exactly this reason.
- **Don't let exceptions escape from tool functions into the agent loop**
  — wrap them in the dispatcher's try/except so the agent sees an error
  result, not a Python traceback.
- **Don't commit `.env`.** It's gitignored, but double-check before
  pushing.
- **Don't bypass the `integration` marker.** Live network calls stay out
  of the default `pytest` run.
- **Don't present Duffel test-mode prices to a user as if they were real
  quotes** — flag them as sandbox data.
