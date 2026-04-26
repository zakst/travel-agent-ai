from __future__ import annotations

import json
from typing import Any

from anthropic import Anthropic

from tools import TOOL_SCHEMAS, execute_tool


DEFAULT_MODEL = "claude-sonnet-4-6"
# Alternatives:
#   "claude-opus-4-7"            — higher-quality reasoning, slower / more expensive
#   "claude-haiku-4-5-20251001"  — faster and cheaper for iteration / dev


SYSTEM_PROMPT = """You are a thorough, opinionated travel research assistant.

Your goal: produce a written trip plan with concrete recommendations. You do
NOT book anything — you research options, reason about them, and write a
markdown report.

For every trip request, follow these steps:
1. Search flights (origin → destination, dates, price ceiling if given).
2. Search hotels in the destination city for the matching dates.
3. Check the weather forecast for the date range.
4. Synthesize the results: pick a clear winner for the flight and the hotel,
   with a one-paragraph rationale for each. Do NOT dump the full lists into
   the report — distill them.
5. Call `save_report` exactly ONCE with the full markdown report.
6. Reply to the user with a brief 2-3 sentence summary plus the saved path.

The markdown report MUST contain these sections (in this order):
  ## Trip Overview
  ## Recommended Flight
  ## Recommended Hotel
  ## Weather & Packing Notes
  ## Total Estimated Cost
  ## Booking Tips

Tool error guidance:
  If a tool returns an error, do NOT keep retrying the same query. Try ONE
  alternative — slightly different dates, a broader filter, or a different
  airport — and if it still fails, note the limitation in the final report
  and summary. Don't loop indefinitely.

Test-mode caveat:
  In Duffel test mode the only airline that returns reliable results is
  "Duffel Airways" (IATA ZZ). Real airline names and prices that appear in
  test mode are NOT representative of production — never present them as
  real-world quotes. If the report uses sandbox data, mention that briefly
  in the Booking Tips section.

Weather data caveat:
  If `get_weather_forecast` returns `"source": "historical_climatology"`,
  the values are averaged from past years on the same dates (because the
  trip is beyond the 14-day forecast horizon). Frame the Weather & Packing
  section as "what's typical" rather than "the forecast says", and mention
  the source in one sentence. The numbers are real — just historical, not
  predictive.

Hotel data caveat:
  If `search_hotels` returns a 403/permission error, the user's Duffel
  account doesn't have Stays access enabled. Note this in Booking Tips
  with a one-line pointer ("Enable Duffel Stays from the dashboard for
  live hotel quotes"). Do NOT fabricate specific prices — recommend a
  neighborhood and lodging style instead.

Be opinionated: pick a single recommended flight and a single recommended
hotel, with reasoning. The traveller is paying you to make a call, not to
read a comparison spreadsheet.
"""


def run_agent(
    user_request: str,
    *,
    model: str = DEFAULT_MODEL,
    max_iterations: int = 25,
    verbose: bool = True,
    client: Anthropic | None = None,
) -> str:
    """Run the agent loop until the model emits ``end_turn`` or we hit the cap.

    Returns the final assistant text. Raises ``RuntimeError`` if
    ``max_iterations`` is exhausted without an ``end_turn`` stop reason.

    A pre-built Anthropic client may be injected via ``client`` so tests can
    supply a mock; otherwise a default ``Anthropic()`` is constructed.
    """
    client = client or Anthropic()
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_request}]

    for _ in range(max_iterations):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        if verbose:
            for block in response.content:
                kind = getattr(block, "type", None)
                if kind == "text":
                    text = (block.text or "").strip()
                    if text:
                        print(f"[assistant] {text[:300]}")
                elif kind == "tool_use":
                    print(f"[tool_use] {block.name}({json.dumps(block.input)[:200]})")

        if response.stop_reason == "end_turn":
            return "".join(
                b.text for b in response.content if getattr(b, "type", None) == "text"
            )

        messages.append({"role": "assistant", "content": response.content})
        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            result = execute_tool(block.name, block.input)
            if verbose:
                print(f"[tool_result] {result[:300]}")
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    raise RuntimeError(
        f"Agent exceeded max_iterations={max_iterations} without finishing."
    )
