"""Chạy bảy công đoạn của đồ án từ CSV nguồn tới bảng tín hiệu theo County."""

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from statistics import mean
from time import perf_counter

from pyarrow import csv as arrow_csv, parquet

from grafana_dashboard import build_dashboard
from quy_tac_du_lieu import input_header
from truc_quan_hoa import build_payload, render


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(columns)
        writer.writerows(rows)


def sha256(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def inspect_source(source, version, destination):
    metadata = {
        "dataset": "Irish Property Price Register",
        "distribution": "Kaggle",
        "url": "https://www.kaggle.com/datasets/fionnhughes/property-price-register",
        "version": version,
        "filename": source.name,
        "columns": input_header(source),
        "bytes": source.stat().st_size,
        "sha256": sha256(source),
    }
    write_json(destination / "source.json", metadata)
    return metadata


def ingest(source, metadata, destination):
    staged = destination / source.name
    chunk_size = 1024 * 1024
    digest = hashlib.sha256()
    bytes_written = chunks = 0
    with source.open("rb") as incoming, staged.open("xb") as outgoing:
        for chunk in iter(lambda: incoming.read(chunk_size), b""):
            outgoing.write(chunk)
            digest.update(chunk)
            bytes_written += len(chunk)
            chunks += 1
    if bytes_written != metadata["bytes"] or digest.hexdigest() != metadata["sha256"]:
        raise ValueError("Tệp thu nạp khác tệp nguồn đã kiểm tra.")
    write_json(destination / "receipt.json", {
        "mode": "python_batch_producer",
        "chunks": chunks,
        "chunk_size_bytes": chunk_size,
        "filename": staged.name,
        "bytes": metadata["bytes"],
        "sha256": metadata["sha256"],
        "received_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    return staged


def store_raw(staged, metadata, destination):
    version = destination / "raw" / metadata["sha256"]
    version.mkdir(parents=True)
    stored = staged.rename(version / staged.name)
    table = version / "transactions.parquet"
    reader = arrow_csv.open_csv(
        stored,
        convert_options=arrow_csv.ConvertOptions(
            column_types=dict.fromkeys(metadata["columns"], "string"),
            strings_can_be_null=True,
            null_values=[""],
        ),
    )
    rows = 0
    with parquet.ParquetWriter(table, reader.schema, compression="snappy") as writer:
        for batch in reader:
            writer.write_batch(batch)
            rows += batch.num_rows
    write_json(destination / "catalog.json", {
        **metadata,
        "format": "CSV",
        "path": stored.relative_to(destination).as_posix(),
        "parquet": {
            "path": table.relative_to(destination).as_posix(),
            "compression": "snappy",
            "bytes": table.stat().st_size,
            "sha256": sha256(table),
            "rows": rows,
        },
    })
    return stored, table


def process(stored, table, destination):
    script = Path(__file__).with_name("phan_tich.py")
    log_path = destination / "spark.log"
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(script), str(stored), "--parquet", str(table),
             "--output", str(destination / "tables")],
            stdout=log, stderr=subprocess.STDOUT,
        )
    if result.returncode:
        tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
        raise RuntimeError("PySpark xử lý thất bại.\n" + "\n".join(tail))
    return destination / "tables"


def analyze(tables, cutoff, destination):
    payload = build_payload(tables, cutoff)
    write_json(destination / "analysis.json", payload)

    metrics, forecasts, validation = [], [], []
    choices, scores = Counter(), {}
    better_than_baseline = 0
    history_length = payload["historyLength"]
    periods = payload["periods"]
    for county, county_data in payload["counties"].items():
        result = county_data["forecast"]
        if result is None:
            continue
        selected = result["model"]
        choices[selected] += 1
        better_than_baseline += result["holdout"][selected][0] < result["holdout"]["last_value"][0]
        for model, (mae, rmse) in result["holdout"].items():
            scores.setdefault(model, []).append((mae, rmse))
            metrics.append((county, model, model == selected, result["origins"],
                            result["development"][model], mae, rmse))
        for period, (point, low, high) in zip(periods[history_length:], result["points"], strict=True):
            forecasts.append((county, period, selected, point, low, high))
        holdout_periods = periods[history_length - payload["horizon"]:history_length]
        for period, (actual, fixed), rolling, fixed_band, rolling_band in zip(
            holdout_periods, result["holdoutPoints"], result["rollingPoints"],
            result["holdoutBand"], result["rollingBand"], strict=True,
        ):
            validation.append((county, period, selected, actual, fixed, *fixed_band,
                               rolling, *rolling_band))

    write_csv(destination / "model_metrics.csv",
              ("county", "model", "selected", "development_origins", "development_mae_eur",
               "holdout_mae_eur", "holdout_rmse_eur"), metrics)
    write_csv(destination / "forecast_quarters.csv",
              ("county", "quarter", "model", "median_eur", "low_eur", "high_eur"), forecasts)
    write_csv(destination / "holdout_predictions.csv",
              ("county", "quarter", "model", "actual_eur", "fixed_eur", "fixed_low_eur",
               "fixed_high_eur", "rolling_eur", "rolling_low_eur", "rolling_high_eur"), validation)
    write_json(destination / "evaluation.json", {
        "last_observed_quarter": periods[history_length - 1],
        "forecast_start": periods[history_length],
        "forecast_end": periods[-1],
        "counties_with_forecast": choices.total(),
        "counties_without_forecast": [
            county for county, data in payload["counties"].items() if data["forecast"] is None
        ],
        "selected_models": dict(choices),
        "selected_strictly_better_than_last_value_by_holdout_mae": better_than_baseline,
        "average_of_county_holdout_metrics_eur": {
            model: {"mae": round(mean(pair[0] for pair in values), 2),
                    "rmse": round(mean(pair[1] for pair in values), 2)}
            for model, values in scores.items()
        },
    })


def present(analysis, destination):
    payload = json.loads(analysis.read_text(encoding="utf-8"))
    (destination / "dashboard.html").write_text(render(payload), encoding="utf-8")
    write_json(destination / "grafana_dashboard.json", build_dashboard(payload))


def decide(analysis, threshold, destination):
    payload = json.loads(analysis.read_text(encoding="utf-8"))
    current_index = payload["historyLength"] - 1
    previous_index = current_index - 4
    min_count = payload["minTransactions"]
    actions = {
        "review_increase": "Rà soát nguyên nhân tăng và cơ cấu giao dịch",
        "review_decrease": "Rà soát nguyên nhân giảm và cơ cấu giao dịch",
        "monitor": "Tiếp tục theo dõi quý sau",
        "insufficient_data": "Kiểm tra độ đầy đủ trước khi diễn giải",
    }
    rows, counts = [], Counter()
    for county, data in payload["counties"].items():
        current = data["observed"][current_index]
        previous = data["observed"][previous_index] if previous_index >= 0 else None
        change = None
        status = "insufficient_data"
        if current and previous and min(current[1], previous[1]) >= min_count:
            change = (Decimal(str(current[0])) / Decimal(str(previous[0])) - 1) * 100
            status = "monitor"
            if change >= threshold:
                status = "review_increase"
            elif change <= -threshold:
                status = "review_decrease"
        counts[status] += 1
        rows.append((county, *(current or (None, None)), *(previous or (None, None)),
                     None if change is None else format(change, ".4f"), status, actions[status]))

    write_csv(destination / "county_actions.csv",
              ("county", "current_median_eur", "current_transactions", "previous_median_eur",
               "previous_transactions", "yoy_pct", "signal", "suggested_action"), rows)
    write_json(destination / "decision_summary.json", {
        "quarter": payload["periods"][current_index],
        "comparison_quarter": payload["periods"][previous_index] if previous_index >= 0 else None,
        "min_transactions_each_quarter": min_count,
        "absolute_yoy_threshold_pct": str(threshold),
        "counts": dict(counts),
        "purpose": "Tín hiệu rà soát theo giá giao dịch quan sát",
    })


def run_pipeline(source, version, cutoff, threshold, output):
    output.mkdir(parents=True, exist_ok=False)
    stages = []

    def step(name, inputs, result, operation, *args):
        destination = output / name
        destination.mkdir()
        print(f"[{len(stages) + 1}/7] {name}", flush=True)
        start = perf_counter()
        value = operation(*args, destination)
        stages.append({
            "stage": name, "inputs": inputs, "outputs": result,
            "seconds": round(perf_counter() - start, 3),
        })
        return value

    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    metadata = step("01_sources", [source.name], ["01_sources/source.json"],
                    inspect_source, source, version)
    staged_file = f"02_ingestion/{source.name} (tệp tạm)"
    staged = step("02_ingestion", ["01_sources/source.json", source.name],
                  ["02_ingestion/receipt.json", staged_file], ingest, source, metadata)
    stored, table = step("03_storage", [staged_file], ["03_storage/catalog.json", "03_storage/raw/"],
                         store_raw, staged, metadata)
    tables = step("04_processing", [table.relative_to(output).as_posix(),
                                    stored.relative_to(output).as_posix()],
                  ["04_processing/tables/", "04_processing/spark.log"], process, stored, table)
    step("05_analytics", ["04_processing/tables/prices_by_quarter.csv",
                          "04_processing/tables/quality.json"],
         ["05_analytics/analysis.json", "05_analytics/evaluation.json",
          "05_analytics/model_metrics.csv", "05_analytics/holdout_predictions.csv",
          "05_analytics/forecast_quarters.csv"], analyze, tables, cutoff)
    analysis = output / "05_analytics/analysis.json"
    step("06_presentation", ["05_analytics/analysis.json"], ["06_presentation/dashboard.html",
                                                            "06_presentation/grafana_dashboard.json"],
         present, analysis)
    step("07_decision_action", ["05_analytics/analysis.json"], [
        "07_decision_action/county_actions.csv", "07_decision_action/decision_summary.json",
    ], decide, analysis, threshold)
    manifest = output / ".run_manifest.tmp"
    write_json(manifest, {
        "started_at_utc": started_at,
        "python_version": sys.version.split()[0],
        "source": metadata,
        "stages": stages,
    })
    manifest.rename(output / "run_manifest.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="CSV nguồn của Irish Property Price Register.")
    parser.add_argument("--output", type=Path, required=True, help="Thư mục kết quả mới.")
    parser.add_argument("--source-version", default="Kaggle v6")
    parser.add_argument("--through", default="2026-Q2", help="Quý quan sát cuối theo dạng YYYY-Qn.")
    parser.add_argument("--alert-yoy-pct", type=Decimal, default=Decimal("10"))
    args = parser.parse_args()
    quarter = re.fullmatch(r"([0-9]{4})-Q([1-4])", args.through)
    if not quarter or int(quarter[1]) < 1:
        parser.error("--through phải có dạng YYYY-Q1 đến YYYY-Q4.")
    cutoff = int(quarter[1]) * 4 + int(quarter[2]) - 1
    if not args.alert_yoy_pct.is_finite() or args.alert_yoy_pct <= 0:
        parser.error("--alert-yoy-pct phải là số hữu hạn lớn hơn 0.")
    if not args.csv.is_file():
        parser.error(f"Không tìm thấy tệp CSV: {args.csv}")
    if args.output.exists():
        parser.error(f"Thư mục kết quả đã tồn tại: {args.output}")
    run_pipeline(args.csv.resolve(), args.source_version, cutoff, args.alert_yoy_pct,
                 args.output.resolve())
    print(f"Hoàn thành: {args.output}")


if __name__ == "__main__":
    main()
