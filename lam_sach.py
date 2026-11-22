"""Xuất giao dịch đã làm sạch và số liệu kiểm tra chất lượng."""

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from quy_tac_du_lieu import (
    COUNTIES, COUNTY_PREFIX, FALSE_FLAGS, HIGH_PRICE, INPUT_COLUMNS, LOW_PRICE,
    NEW_IRISH, NEW_PATTERN, PRICE_FORMAT, SECOND_HAND_IRISH, SECOND_HAND_PATTERN,
    TRUE_FLAGS, input_header,
)


OUTPUT_COLUMNS = (
    "source_record", "sale_date", "county", "price_eur", "property_type",
    "property_size", "suspected_duplicate", "price_for_review",
)
FLAGS = dict.fromkeys(TRUE_FLAGS, True) | dict.fromkeys(FALSE_FLAGS, False)


def records(source):
    with source.open(encoding="utf-8-sig", newline="") as file:
        for number, row in enumerate(csv.DictReader(file, strict=True), 1):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Bản ghi {number} có số cột không khớp lược đồ.")
            yield number, row


def record_key(row):
    # Mã băm của chín trường CSV, theo thứ tự cột cố định.
    values = [row[column] for column in INPUT_COLUMNS]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode("utf-8")).digest()


def parse_date(value):
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value)
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        return None


def property_type(description):
    if re.match(SECOND_HAND_PATTERN, description) or description == SECOND_HAND_IRISH:
        return "second_hand"
    if re.match(NEW_PATTERN, description) or description in NEW_IRISH:
        return "new"
    return None


def clean(source, destination):
    input_header(source)
    frequencies = Counter(record_key(row) for _, row in records(source))
    counts = dict.fromkeys((
        "raw_rows", "clean_rows", "excluded_rows", "invalid_date_rows",
        "invalid_county_rows", "invalid_price_rows", "unknown_property_type_rows",
        "unknown_market_flag_rows", "unknown_vat_flag_rows", "non_market_price_rows",
        "vat_exclusive_rows", "missing_eircode_rows", "missing_property_size_rows",
        "eligible_second_hand_rows", "eligible_new_rows", "clean_rows_in_duplicate_groups",
        "clean_price_at_or_below_low_threshold", "clean_price_at_or_above_high_threshold",
    ), 0)
    counties = set()
    first_sale, last_sale = date.max, date.min
    min_price, max_price = Decimal("Infinity"), Decimal("0")

    with (destination / "transactions_clean.csv").open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(OUTPUT_COLUMNS)
        for number, row in records(source):
            sale_date = parse_date(row["date_of_sale"].strip())
            county = re.sub(COUNTY_PREFIX, "", row["county"].strip()).title()
            price_text = row["price_eur"].strip().removeprefix("€").strip()
            price = (
                Decimal(price_text.replace(",", ""))
                if re.fullmatch(PRICE_FORMAT, price_text) else None
            )
            kind = property_type(row["description"].strip().lower())
            market_flag = FLAGS.get(row["not_full_market_price"].strip().lower())
            vat_flag = FLAGS.get(row["vat_exclusive"].strip().lower())
            size = row["property_size"].strip()
            issues = {
                "invalid_date_rows": sale_date is None,
                "invalid_county_rows": county not in COUNTIES,
                "invalid_price_rows": price is None or not 0 < price < 10**14,
                "unknown_property_type_rows": kind is None,
                "unknown_market_flag_rows": market_flag is None,
                "unknown_vat_flag_rows": vat_flag is None,
                "non_market_price_rows": market_flag is True,
                "vat_exclusive_rows": vat_flag is True,
            }
            counts["raw_rows"] += 1
            counts["missing_eircode_rows"] += not row["eircode"].strip()
            counts["missing_property_size_rows"] += not size
            for issue, occurred in issues.items():
                counts[issue] += occurred
            if any(issues.values()):
                counts["excluded_rows"] += 1
                continue

            suspected_duplicate = frequencies[record_key(row)] > 1
            low_price = price <= LOW_PRICE
            high_price = price >= HIGH_PRICE
            counts["clean_rows"] += 1
            counts[f"eligible_{kind}_rows"] += 1
            counts["clean_rows_in_duplicate_groups"] += suspected_duplicate
            counts["clean_price_at_or_below_low_threshold"] += low_price
            counts["clean_price_at_or_above_high_threshold"] += high_price
            counties.add(county)
            first_sale, last_sale = min(first_sale, sale_date), max(last_sale, sale_date)
            min_price, max_price = min(min_price, price), max(max_price, price)
            writer.writerow((
                number, sale_date, county, f"{price:.2f}", kind, size,
                int(suspected_duplicate), int(low_price or high_price),
            ))

    with source.open("rb") as file:
        source_sha256 = hashlib.file_digest(file, "sha256").hexdigest()
    quality = {
        "engine": "Python standard library",
        "source_file": source.name,
        "source_sha256": source_sha256,
        **counts,
        "raw_duplicate_groups": sum(count > 1 for count in frequencies.values()),
        "raw_extra_copies": sum(count - 1 for count in frequencies.values()),
        "clean_counties": len(counties),
        "clean_first_sale": str(first_sale) if counties else None,
        "clean_last_sale": str(last_sale) if counties else None,
        "clean_min_price_eur": f"{min_price:.2f}" if counties else None,
        "clean_max_price_eur": f"{max_price:.2f}" if counties else None,
        "review_low_price_eur": LOW_PRICE,
        "review_high_price_eur": HIGH_PRICE,
    }
    (destination / "cleaning_quality.json").write_text(
        json.dumps(quality, indent=2) + "\n", encoding="utf-8"
    )
    return quality


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="CSV gốc từ Irish Property Price Register.")
    parser.add_argument("--output", required=True, type=Path, help="Thư mục kết quả mới.")
    args = parser.parse_args()
    source = args.csv.resolve()
    output = args.output.resolve()
    if not source.is_file():
        parser.error(f"Không tìm thấy CSV: {source}")
    if output.exists():
        parser.error(f"Thư mục kết quả đã tồn tại: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix=".cleaning-") as temp:
        staging = Path(temp) / "result"
        staging.mkdir()
        quality = clean(source, staging)
        staging.rename(output)
    print(f"Giữ {quality['clean_rows']:,}/{quality['raw_rows']:,} giao dịch. Kết quả: {output}")


if __name__ == "__main__":
    main()
