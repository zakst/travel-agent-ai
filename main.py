from __future__ import annotations

import sys

from dotenv import load_dotenv

from agent import run_agent


DEFAULT_REQUEST = (
    "Plan a one-week trip from San Francisco (SFO) to Tokyo (NRT). "
    "Depart 2026-06-15, return 2026-06-22. Flight under $1200. "
    "Hotel near central Tokyo for under $300/night. Walkability matters."
)


def main() -> int:
    """CLI entry point: load .env, dispatch the request, print the final summary."""
    load_dotenv()
    request = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REQUEST
    try:
        final = run_agent(request, verbose=True)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print("\n" + "=" * 60)
    print(final)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
