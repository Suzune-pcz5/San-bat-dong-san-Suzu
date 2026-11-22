"""Dự báo theo County và tạo dashboard từ kết quả Spark hoặc CSV sạch."""

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from statistics import median

from du_bao_co_so import period_date, period_number
from du_bao_thi_truong import HORIZON, MIN_TRANSACTIONS, MODEL_NAMES, forecast_county
from quy_tac_du_lieu import COUNTIES


QUALITY_FIELDS = (
    "raw_rows", "excluded_rows", "missing_eircode_rows", "missing_property_size_rows",
)


def quarter_label(q):
    year, quarter = divmod(q, 4)
    return f"{year}-Q{quarter + 1}"


def summarize(source, cutoff):
    groups = defaultdict(list)
    types = Counter()
    latest = date.min
    earliest = date.max
    flagged = 0
    with source.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            day = date.fromisoformat(row["sale_date"])
            kind = row["property_type"]
            county = row["county"]
            if county not in COUNTIES or kind not in ("second_hand", "new"):
                raise ValueError(f"County hoặc loại nhà ngoài lược đồ: {county}, {kind}")
            earliest, latest = min(earliest, day), max(latest, day)
            types[kind] += 1
            flagged += row.get("price_for_review") == "1"
            quarter = period_number(day, 3)
            if kind == "second_hand" and quarter <= cutoff:
                price = Decimal(row["price_eur"])
                if not price.is_finite() or price <= 0:
                    raise ValueError("CSV sạch có giá không hợp lệ.")
                groups[county, quarter].append(price)
    history = defaultdict(dict)
    for (county, q), values in sorted(groups.items()):
        price = median(values).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        history[county][q] = [float(price), len(values)]
    meta = {
        "firstDate": earliest.isoformat(), "lastDate": latest.isoformat(), "types": dict(types),
        "cleanRows": sum(types.values()), "reviewRows": flagged,
        "observedRows": sum(n for rows in history.values() for _, n in rows.values()),
    }
    quality_path = source.with_name("cleaning_quality.json")
    if quality_path.is_file():
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
        if (quality["eligible_second_hand_rows"], quality["eligible_new_rows"]) == (
            types["second_hand"], types["new"]
        ):
            meta["quality"] = {key: quality[key] for key in QUALITY_FIELDS}
    return history, meta


def read_spark_summary(source, cutoff):
    quality = json.loads((source / "quality.json").read_text(encoding="utf-8"))
    history = defaultdict(dict)
    types = Counter()
    with (source / "prices_by_quarter.csv").open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            county, kind = row["county"], row["property_type"]
            if county not in COUNTIES or kind not in ("second_hand", "new"):
                raise ValueError(f"County hoặc loại nhà ngoài lược đồ: {county}, {kind}")
            day = date.fromisoformat(row["period_start"])
            quarter = period_number(day, 3)
            if day != period_date(quarter, 3):
                raise ValueError(f"Ngày {day} không phải đầu quý.")
            price, transactions = Decimal(row["median_eur"]), int(row["transactions"])
            if not price.is_finite() or price <= 0 or transactions < 1:
                raise ValueError(f"Giá hoặc số giao dịch không hợp lệ: {county}, {day}.")
            types[kind] += transactions
            if kind == "second_hand" and quarter <= cutoff:
                if quarter in history[county]:
                    raise ValueError(f"Trùng quý {day} của {county}.")
                history[county][quarter] = [float(price), transactions]

    expected_types = {
        "second_hand": quality["eligible_second_hand_rows"],
        "new": quality["eligible_new_rows"],
    }
    if types != Counter(expected_types) or types.total() != quality["clean_rows"]:
        raise ValueError("Số giao dịch trong bảng quý không khớp quality.json.")
    meta = {
        "firstDate": quality["clean_first_sale"],
        "lastDate": quality["clean_last_sale"],
        "types": dict(types),
        "cleanRows": quality["clean_rows"],
        "reviewRows": (
            quality["clean_price_at_or_below_low_threshold"]
            + quality["clean_price_at_or_above_high_threshold"]
        ),
        "observedRows": sum(n for rows in history.values() for _, n in rows.values()),
        "quality": {key: quality[key] for key in QUALITY_FIELDS},
    }
    return history, meta


def build_payload(source, cutoff):
    history, meta = (
        read_spark_summary(source, cutoff) if source.is_dir() else summarize(source, cutoff)
    )
    if not any(cutoff in rows for rows in history.values()):
        raise ValueError("Quý được chọn không có giao dịch nhà cũ.")
    start = min(min(rows) for rows in history.values())
    counties = {}
    for county, rows in history.items():
        forecast = forecast_county(rows, cutoff)
        counties[county] = {
            "observed": [rows.get(q) for q in range(start, cutoff + 1)],
            "forecast": forecast,
        }
    return {
        "periods": [quarter_label(q) for q in range(start, cutoff + HORIZON + 1)],
        "historyLength": cutoff - start + 1,
        "horizon": HORIZON,
        "counties": counties,
        "minTransactions": MIN_TRANSACTIONS,
        "models": MODEL_NAMES,
        "meta": meta,
    }


def render(payload):
    assets = Path(__file__).with_name("dashboard")
    template = (assets / "index.html").read_text(encoding="utf-8")
    tokens = {
        "CSS": (assets / "style.css").read_text(encoding="utf-8"),
        "JS": (assets / "chart.js").read_text(encoding="utf-8"),
        "DATA": json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c"),
    }
    return re.sub(r"__(CSS|JS|DATA)__", lambda match: tokens[match[1]], template)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source", type=Path, help="Thư mục kết quả của phan_tich.py hoặc tệp CSV sạch."
    )
    parser.add_argument("--through", default="2026-Q2")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    match = re.fullmatch(r"([0-9]{4})-Q([1-4])", args.through)
    if not match:
        parser.error("--through phải có dạng YYYY-Q1 đến YYYY-Q4.")
    cutoff = int(match[1]) * 4 + int(match[2]) - 1
    payload = build_payload(args.source, cutoff)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as file:
        file.write(render(payload))
    print(f"Dashboard generated for {len(payload['counties'])} counties.")


if __name__ == "__main__":
    main()
