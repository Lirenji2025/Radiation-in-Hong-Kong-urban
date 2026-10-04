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


def dose_tier(value: float | None) -> int:
    """Map a dose rate to one of the five legend tiers; use -1 for missing data."""
    if value is None:
        return -1
    if value < 0.08:
        return 0
    if value < 0.10:
        return 1
    if value < 0.12:
        return 2
    if value < 0.14:
        return 3
    return 4


def skull_markup(tier: int, x: float, y: float, size: float = 1) -> str:
    """Draw the matching severity-specific skull silhouette for the SVG preview."""
    tier_class = f"tier-{tier}" if tier >= 0 else "tier-na"
    crack = '<path class="detail" d="M1-16l-3 6 4 3-3 4"/>' if tier in (1, 3, 4) else ""
    horns = ""
    crown = ""
    if tier >= 2:
        horns = (
            '<path class="horn" d="M-11-11l-5-8 1 11zM11-11l5-8-1 11z"/>'
            if tier == 2
            else '<path class="horn" d="M-10-12l-9-11 4 16zM10-12l9-11-4 16z"/>'
        )
    if tier == 4:
        crown = '<path class="horn" d="M-7-16l-3-9 8 7zM0-18v-9l5 9zM7-16l5-8v10z"/>'
    return (
        f'<g class="skull {tier_class}" transform="translate({x} {y}) scale({size})">'
        '<path class="body" d="M0-18c-10 0-16 8-16 18 0 7 4 11 8 13v7H8v-7c4-2 8-6 8-13 0-10-6-18-16-18z"/>'
        '<circle class="cutout" cx="-6" cy="1" r="3.6"/><circle class="cutout" cx="6" cy="1" r="3.6"/>'
        '<path class="cutout" d="M0 5l-2.5 4h5z"/><path class="detail" d="M-7 12H7M-4 12v6M0 12v6M4 12v6"/>'
        f"{crack}{horns}{crown}</g>"
    )


def make_preview(data: dict) -> str:
    """Make a static theme-park-style map still from the last hourly observation."""
    last_index = len(data["timestamps"]) - 1
    marks = []
    label_offsets = {
        "KP": (-8, 25, "end"), "KT": (16, -8, "start"), "SWH": (16, 24, "start"),
        "KO": (-12, -12, "end"), "TM": (12, 19, "start"), "STK": (8, 15, "start"),
        "YNF": (-12, 20, "end"), "GFS": (-8, -8, "end"), "CD": (8, 14, "start"),
    }
    for station in data["stations"]:
        value = data["readings"][station["code"]][last_index]
        offset_x, offset_y, anchor = label_offsets.get(station["code"], (8, 20, "start"))
        label_x = station["x"] + offset_x
        label_y = station["y"] + offset_y
        marks.append(
            f'<g><title>{station["name"]}: {"NA" if value is None else f"{value:.3f} µSv/h"}</title>'
            f'{skull_markup(dose_tier(value), station["x"], station["y"], (0.62, 0.7, 0.8, 0.91, 1.02)[max(0, dose_tier(value))])}</g>'
            f'<text x="{label_x}" y="{label_y}" text-anchor="{anchor}" class="place">{station["name"]}</text>'
        )
    legend = []
    legend_ranges = ("I  &lt;0.08", "II  0.08–&lt;0.10", "III  0.10–&lt;0.12", "IV  0.12–&lt;0.14", "V  ≥0.14", "NA")
    for tier, label in enumerate(legend_ranges):
        level = -1 if tier == 5 else tier
        x = 42 + tier * 130
        legend.append(skull_markup(level, x + 10, 724, 0.43))
        legend.append(f'<text x="{x + 27}" y="728" class="legend-label">{label}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 860 760" role="img" aria-label="Hong Kong gamma radiation skull map">
<style>
  .land {{ fill:#d9e8b7; stroke:#fff4d8; stroke-width:7 }} .island {{ fill:#c9e2ad; stroke:#fff4d8; stroke-width:5 }}
  .zone {{ stroke:#f8f0d8; stroke-width:2; opacity:.82 }} .wood {{ fill:#b6d69c }} .meadow {{ fill:#e8e9a9 }} .cliff {{ fill:#b6d7bb }}
  .road-case {{ fill:none; stroke:#fff5dc; stroke-width:10; stroke-linecap:round }} .road {{ fill:none; stroke:#e89b79; stroke-width:5; stroke-linecap:round }} .trail {{ fill:none; stroke:#a76d91; stroke-width:3; stroke-dasharray:2 9; stroke-linecap:round }}
  .wave {{ fill:none; stroke:#82c2bd; stroke-width:2; opacity:.7 }} .tree {{ fill:#437a61; stroke:#f8f0d8; stroke-width:1.5; stroke-linejoin:round }} .trunk {{ fill:#936d53; stroke:none }}
  .body,.horn {{ fill:currentColor; stroke:#fff; stroke-width:1.3; stroke-linejoin:round }} .cutout {{ fill:#f8f7ed }} .detail {{ fill:none; stroke:#f8f7ed; stroke-width:1.7; stroke-linecap:round; stroke-linejoin:round }}
  .tier-0 {{ color:#477d76 }} .tier-1 {{ color:#66732f }} .tier-2 {{ color:#8c5a24 }} .tier-3 {{ color:#8e3727 }} .tier-4 {{ color:#49182d }} .tier-na {{ color:#68736f }}
  .place {{ fill:#243a31; font:600 12px Arial; paint-order:stroke; stroke:#d9e8b7; stroke-width:4px }} .region {{ fill:#40584b; font:700 17px Arial; paint-order:stroke; stroke:#d9e8b7; stroke-width:5px }} .water-label {{ fill:#477f82; font:italic 15px Arial }}
  .title {{ fill:#263c32; font:700 28px Arial }} .sub {{ fill:#536b5d; font:14px Arial }} .legend-label {{ fill:#263c32; font:10px Arial }}
</style>
<rect width="860" height="760" fill="#afd8d1"/><path class="wave" d="M22 176q15-8 30 0t30 0M40 497q15-8 30 0t30 0M710 523q15-8 30 0t30 0M292 682q15-8 30 0t30 0"/>
<path class="land" d="M72 333 C87 318 91 300 83 284 C75 266 82 247 99 232 C111 218 104 202 117 188 C129 172 151 176 159 154 C165 135 187 127 201 143 C216 159 234 150 249 136 C264 123 282 135 293 151 C308 168 325 163 340 149 C354 135 371 141 381 157 C394 175 410 169 425 154 C441 139 459 146 470 162 C482 178 499 177 513 162 C529 145 547 151 560 168 C573 183 590 179 606 166 C622 151 641 157 653 173 C668 190 687 179 701 160 C715 140 738 145 749 165 C762 184 781 182 790 197 C800 213 786 228 770 239 C754 251 754 267 771 279 C787 294 780 310 762 319 C744 330 749 345 766 356 C780 370 769 385 750 389 C733 395 733 411 719 425 C704 442 685 444 671 429 C656 413 638 417 624 437 C610 456 592 454 579 435 C567 418 551 415 536 431 C518 450 503 462 489 478 C472 496 458 509 444 516 C427 528 410 516 404 498 C395 477 388 462 372 456 C355 449 345 460 332 479 C318 499 301 504 288 489 C276 473 278 456 265 444 C252 431 240 440 226 455 C211 470 196 478 181 465 C167 453 165 440 148 439 C130 438 115 426 106 412 C96 399 81 397 75 381 C69 365 78 349 72 333Z"/>
<path class="island" d="M287 544 C302 524 324 523 340 534 C360 519 381 521 397 535 C416 520 438 523 452 538 C471 526 492 535 502 551 C522 546 540 559 545 576 C565 584 574 600 565 615 C570 631 555 644 539 642 C523 656 503 650 490 642 C474 654 455 649 444 639 C428 651 408 647 396 636 C377 645 357 636 350 623 C332 631 312 618 313 600 C293 598 282 580 291 565Z"/>
<path class="island" d="M76 585 C88 568 103 567 115 580 C128 570 144 577 149 591 C166 583 183 592 186 607 C206 603 222 614 227 629 C246 625 264 638 265 654 C268 670 252 682 235 676 C220 691 198 688 187 677 C171 689 151 682 144 670 C126 682 105 670 105 653 C88 656 73 644 76 629 C64 616 65 597 76 585Z"/>
<path class="island" d="M265 599 C273 586 285 584 294 594 C304 590 313 598 310 608 C318 617 311 629 301 630 C292 640 280 636 277 627 C265 625 260 611 265 599Z M277 667 C284 654 295 653 302 661 C311 668 307 682 298 686 C286 690 275 681 277 667Z M566 568 C576 555 591 555 599 567 C607 578 600 592 588 594 C574 593 564 582 566 568Z M638 531 C646 520 657 522 663 532 C668 542 662 552 651 552 C640 549 635 541 638 531Z"/>
<path class="zone wood" d="M96 213Q160 165 257 174L286 226Q241 273 152 286L93 258Z"/><path class="zone meadow" d="M301 163Q382 143 465 159L493 218Q440 253 357 247L297 216Z"/><path class="zone wood" d="M501 181Q589 157 696 150L755 202L716 270Q644 247 567 280L502 244Z"/><path class="zone cliff" d="M591 304Q671 286 753 268L770 337L697 374L627 377Z"/><path class="zone meadow" d="M166 394Q237 366 306 384L348 429L279 469L201 465L151 433Z"/>
<path class="trail" d="M119 325Q179 300 228 324T336 329T453 304T582 319T716 286M164 451Q231 420 283 446T391 452T478 477"/>
<g class="tree" transform="translate(137 226)"><path class="trunk" d="M-2 1h4v10h-4z"/><path d="M0-14L-9 0h6l-8 9h22L3 0h6z"/></g><g class="tree" transform="translate(180 205) scale(.8)"><path class="trunk" d="M-2 1h4v10h-4z"/><path d="M0-14L-9 0h6l-8 9h22L3 0h6z"/></g><g class="tree" transform="translate(641 202) scale(.86)"><path class="trunk" d="M-2 1h4v10h-4z"/><path d="M0-14L-9 0h6l-8 9h22L3 0h6z"/></g><g class="tree" transform="translate(685 231) scale(.72)"><path class="trunk" d="M-2 1h4v10h-4z"/><path d="M0-14L-9 0h6l-8 9h22L3 0h6z"/></g>
<path class="road-case" d="M91 359Q177 317 257 337T415 318T567 300T723 254M156 205Q244 235 315 286T443 371T496 451M227 469Q302 426 382 445T511 469"/><path class="road" d="M91 359Q177 317 257 337T415 318T567 300T723 254M156 205Q244 235 315 286T443 371T496 451M227 469Q302 426 382 445T511 469"/>
<text x="420" y="206" class="region" text-anchor="middle">新界 New Territories</text><text x="330" y="424" class="region" text-anchor="middle">九龙 Kowloon</text><text x="412" y="583" class="region" text-anchor="middle">香港岛 Hong Kong Island</text><text x="119" y="624" class="region" text-anchor="middle">大屿山 Lantau</text>
<text x="177" y="278" class="place">元朗 Yuen Long</text><text x="380" y="284" class="place">大埔 Tai Po</text><text x="563" y="351" class="place">西贡 Sai Kung</text><text x="293" y="359" class="place">沙田 Sha Tin</text><text x="566" y="489" class="place">鲤鱼门 Lei Yue Mun</text><text x="357" y="684" class="water-label" text-anchor="middle">南海 South China Sea</text>
<text x="42" y="54" class="title">香港环境伽马辐射 · 骷髅导览图</text><text x="42" y="80" class="sub">{data["timestamps"][-1].replace("T", " ")} HKT · µSv/h</text>
{''.join(marks)}
<rect x="30" y="696" width="800" height="1" fill="#6b9584"/>{''.join(legend)}
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
