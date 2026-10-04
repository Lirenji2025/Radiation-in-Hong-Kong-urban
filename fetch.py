# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Fetch one raw HKO response and keep it unchanged for offline plotting."""

from pathlib import Path
from urllib.request import urlopen


SOURCE_URL = "https://www.hko.gov.hk/radiation/monitoring/data/rmn_hourly_mean_used.txt"
DESTINATION = Path("data/rmn_hourly_mean_used.txt")


def fetch_once() -> None:
    """Save the provider's bytes once; never replace a cached reply by accident."""
    if DESTINATION.exists():
        print(f"Kept existing cached reply: {DESTINATION}")
        return

    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(SOURCE_URL, timeout=30) as response:
        raw_reply = response.read()
    DESTINATION.write_bytes(raw_reply)
    print(f"Saved {len(raw_reply)} unchanged bytes to {DESTINATION}")


if __name__ == "__main__":
    fetch_once()
