# travel-agent-ai

A Python AI agent that researches flights and hotels for a trip and produces a
markdown report with recommendations. **It does NOT book anything** — it
gathers options from real APIs, reasons about them, and writes a report.

## What it does

Give it a free-form trip request and it will:

1. Search flights between the requested origin and destination (Duffel).
2. Search hotels near the destination city (Duffel Stays + Open-Meteo
   geocoding).
3. Pull a daily weather forecast for the date range (Open-Meteo).
4. Reason over the options, pick a single recommended flight and hotel, and
   save a structured markdown report under `reports/`.

Sample request:

> Plan a one-week trip from San Francisco (SFO) to Tokyo (NRT). Depart
> 2026-06-15, return 2026-06-22. Flight under $1200. Hotel near central
> Tokyo for under $300/night. Walkability matters.

## How it works

```
   ┌──────────────────────────┐
   │  user request (string)   │
   └────────────┬─────────────┘
                ▼
   ┌──────────────────────────┐         ┌────────────────────────┐
   │  Anthropic Messages API  │ ◄────── │  SYSTEM_PROMPT         │
   │  client.messages.create  │         │  TOOL_SCHEMAS          │
   └────────────┬─────────────┘         └────────────────────────┘
                │
         response.stop_reason
                │
        ┌───────┴────────┐
        │                │
   tool_use          end_turn
        │                │
        ▼                ▼
  execute_tool      final text → user
   (tools.py)
        │
        ▼
   tool_result ──► appended as next user turn ──► loop
```

The agent loop in `agent.py` keeps calling the model. Each turn the model
either issues `tool_use` blocks (we run them, append the results, loop) or
emits `end_turn` (we return the text). After at most `max_iterations`
without an `end_turn` we raise.

## Project layout

| File | Purpose |
| ---- | ------- |
| `tools.py` | Tool JSON schemas, real API implementations, dispatcher |
| `agent.py` | The agent loop + system prompt |
| `main.py` | CLI entry point — loads `.env`, dispatches the request |
| `duffel_client.py` | Thin Duffel REST wrapper (Bearer auth, headers, errors) |
| `geocoding.py` | Open-Meteo city → lat/lon helper (no API key) |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for the two required secrets |
| `pytest.ini` | Pytest config, registers `integration` marker |
| `tests/` | Pytest suite with respx-mocked HTTP |
| `tests/test_integration.py` | Live-API tests (skipped without creds) |

## Setup

1. **Install dependencies.**
   ```bash
   pip install -r requirements.txt
   ```

2. **Get a Duffel test token.** Sign up at
   [duffel.com](https://duffel.com) (~1 minute, no credit card). On the
   dashboard go to **More → Developers → Access Tokens** and create a test
   token — it'll start with `duffel_test_`.

3. **Optional but recommended: enable Duffel Stays.** Hotel search requires
   a one-click access request from the Duffel dashboard. Flight search works
   immediately without it. Approval is usually quick.

4. **Get an Anthropic API key** at
   [console.anthropic.com](https://console.anthropic.com).

5. **Create your `.env`.**
   ```bash
   cp .env.example .env
   ```
   Then fill in the two values in `.env`.

6. **Run it.**
   ```bash
   python main.py
   ```
   That fires off the default Tokyo trip request. To pass your own:
   ```bash
   python main.py "Find me a long weekend in Lisbon, May 8–11 2026, flying from JFK"
   ```

## Important caveat about test mode

In Duffel test mode, the **only airline that returns reliable results is
"Duffel Airways" (IATA `ZZ`)**. Real airline names like ANA or United may
appear in test data, but their prices and schedules are NOT representative
of production. The agent's report is shaped correctly but the data is
sandbox data. To use real airline inventory you need to apply for
production access on the Duffel dashboard.

## API providers

| Provider    | Used for                    | Cost                                  |
| ----------- | --------------------------- | ------------------------------------- |
| Duffel      | Flights + hotels            | Free test mode; production is paid    |
| Open-Meteo  | Weather + geocoding         | Free, no API key                      |
| Anthropic   | LLM reasoning               | Paid per-token (Claude API)           |

## Testing

The test suite uses [respx](https://lundberg.github.io/respx/) to mock all
HTTP, so unit tests run with no network access:

```bash
pytest                 # unit tests only (default)
pytest -m integration  # live-API tests (require real credentials)
```

Integration tests are marked with `@pytest.mark.integration` and skip
themselves when `DUFFEL_ACCESS_TOKEN` is missing. Open-Meteo integration
tests always run because the API needs no key.

## A note on the model

`DEFAULT_MODEL` in `agent.py` is `claude-sonnet-4-6`, a balanced default.
Swap it for one of these for different tradeoffs:

- `claude-opus-4-7` — higher-quality reasoning, slower, more expensive
- `claude-haiku-4-5-20251001` — faster and cheaper, ideal for dev iteration

You can also override per-call:

```python
run_agent("...", model="claude-opus-4-7")
```

## Things to extend

- Persistent memory of past trips for the same traveller
- Multi-city routing (Duffel supports it natively via multiple `slices`)
- Price-drop alerts (poll cheapest flight on a schedule, diff against last run)
- FastAPI streaming UI on top of the agent loop
- A `book_flight` tool gated behind an explicit human-in-the-loop confirmation step

## Limitations

- Open-Meteo forecasts beyond ~14 days out are unreliable.
- The agent **does nothing actually-bookable** — by design. It reads, it
  reasons.
