# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Build the offline interactive map and a static README preview from HKO data."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path


RAW_DATA = Path("data/rmn_hourly_mean_used.txt")
SITE = Path("site")
OUT = Path("out")

STATIONS = {
    "PC": {"name": "Ping Chau", "x": 748, "y": 126},
    "TM": {"name": "Tap Mun", "x": 627, "y": 220},
    "KO": {"name": "Kat O", "x": 559, "y": 166},
    "YNF": {"name": "Yuen Ng Fan", "x": 529, "y": 333},
    "TMT": {"name": "Tai Mei Tuk", "x": 397, "y": 243},
    "STK": {"name": "Sha Tau Kok", "x": 356, "y": 164},
    "KT": {"name": "Kwun Tong", "x": 363, "y": 464},
    "SWH": {"name": "Sai Wan Ho", "x": 393, "y": 506},
    "KP": {"name": "King's Park", "x": 296, "y": 465},
    "TBT": {"name": "Tsim Bei Tsui", "x": 110, "y": 296},
    "CD": {"name": "Cape D'Aguilar", "x": 448, "y": 640},
    "GFS": {"name": "Chek Lap Kok", "x": 102, "y": 590},
}


def parse_radiation_data(raw_text: str) -> dict:
    """Turn HKO's whitespace-delimited station rows into timestamped readings."""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    match = re.search(r"Observation from (\d{10}) to (\d{10})", lines[0])
    if not match:
        raise ValueError("The HKO header did not contain an observation interval.")

    start = datetime.strptime(match.group(1), "%Y%m%d%H")
    end = datetime.strptime(match.group(2), "%Y%m%d%H")
    timestamps = []
    point = start
    while point <= end:
        timestamps.append(point.isoformat(timespec="minutes"))
        point += timedelta(hours=1)

    readings: dict[str, list[float | None]] = {}
    for line in lines[1:]:
        cells = line.split()
        code, values = cells[0], cells[1:]
        if code not in STATIONS:
            continue
        readings[code] = [None if value == "NA" else float(value) for value in values]

    if set(readings) != set(STATIONS):
        raise ValueError("The cached file is missing one or more radiation stations.")
    if any(len(values) != len(timestamps) for values in readings.values()):
        raise ValueError("The number of values does not match the observation interval.")

    return {
        "source": "Hong Kong Observatory Radiation Monitoring Network",
        "sourceUrl": "https://www.hko.gov.hk/en/radiation/monitoring/",
        "unit": "µSv/h",
        "cachedInterval": {"start": timestamps[0], "end": timestamps[-1]},
        "stations": [{"code": code, **details} for code, details in STATIONS.items()],
        "timestamps": timestamps,
        "readings": readings,
    }


def skull_count(value: float | None) -> int:
    """Map dose rate to a readable 1–12 skull scale, preserving missing data."""
    if value is None:
        return 0
    return max(1, min(12, round((value - 0.06) / 0.02) + 1))


def make_preview(data: dict) -> str:
    """Make a static SVG still from the last hourly observation for the README."""
    last_index = len(data["timestamps"]) - 1
    marks = []
    for station in data["stations"]:
        value = data["readings"][station["code"]][last_index]
        skulls = "☠" * skull_count(value)
        marks.append(
            f'<text x="{station["x"]}" y="{station["y"]}" class="skull">{skulls}</text>'
            f'<text x="{station["x"]}" y="{station["y"] + 18}" class="place">{station["name"]} · {value:.2f}</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 860 760" role="img" aria-label="Hong Kong gamma radiation skull map">
<style>
  .water {{ fill:#071d31 }} .land {{ fill:#d9cfb7; stroke:#f6edda; stroke-width:4 }}
  .island {{ fill:#d9cfb7; stroke:#f6edda; stroke-width:3 }} .skull {{ fill:#e44739; font:22px serif; paint-order:stroke; stroke:#071d31; stroke-width:3 }}
  .place {{ fill:#edf4f6; font:12px Arial }} .title {{ fill:#f8f3e8; font:700 28px Arial }} .sub {{ fill:#9cc8ce; font:14px Arial }}
</style>
<rect class="water" width="860" height="760"/><path class="land" d="M68 205 L150 131 254 154 310 111 393 144 471 114 577 161 691 121 786 196 733 284 785 347 680 388 627 459 526 443 449 521 358 486 279 532 203 485 133 511 74 437 105 362Z"/>
<path class="island" d="M178 534q82-42 148 23l-39 72-122-14zM341 552q92-62 171 7l-39 105-130-19zM68 593q45-43 92-12l-4 65-87 21zM525 572q84-47 142 14l-44 78-121-20z"/>
<text x="42" y="54" class="title">香港环境伽马辐射 · skull scale</text><text x="42" y="80" class="sub">{data["timestamps"][-1].replace("T", " ")} HKT · hourly mean · μSv/h</text>
{''.join(marks)}
<rect x="42" y="695" width="776" height="1" fill="#4b7381"/><text x="42" y="728" class="sub">☠ = 0.06–0.08 μSv/h; each additional skull adds 0.02 μSv/h (capped at 12)</text>
</svg>'''


def build() -> None:
    if not RAW_DATA.exists():
        raise SystemExit("No cached HKO reply. Run: uv run fetch.py")
    data = parse_radiation_data(RAW_DATA.read_text(encoding="utf-8-sig"))
    SITE.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    (SITE / "data.js").write_text("window.GAMMA_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")
    shutil.copyfile("app.html", SITE / "index.html")
    (OUT / "hong-kong-gamma-radiation.svg").write_text(make_preview(data), encoding="utf-8")
    print("Built site/index.html and out/hong-kong-gamma-radiation.svg from cached data.")


if __name__ == "__main__":
    build()
