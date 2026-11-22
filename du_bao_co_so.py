"""Dự báo giá trung vị nhà cũ và kiểm định hai mô hình cơ sở."""

import argparse
import csv
import math
from collections import defaultdict
from datetime import date
from pathlib import Path


def period_number(day, months_per_period):
    return (day.year * 12 + day.month - 1) // months_per_period


def period_date(number, months_per_period):
    year, month = divmod(number * months_per_period, 12)
    return date(year, month + 1, 1)


def read_prices(path, months_per_period, cutoff):
    prices = defaultdict(dict)
    with path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if row["property_type"] != "second_hand":
                continue
            day = date.fromisoformat(row["period_start"])
            period = period_number(day, months_per_period)
            if period_date(period, months_per_period) != day:
                raise ValueError(f"Kỳ {day} không phù hợp với --period.")
            series = prices[row["county"]]
            if period <= cutoff and row["meets_count_threshold"].lower() == "true":
                if period in series:
                    raise ValueError(f"Trùng kỳ {day} của {row['county']}.")
                series[period] = float(row["median_eur"])
    return prices


def baselines(series, origin, season, horizon):
    last = series[origin]
    last_season = [series[i] for i in range(origin - season + 1, origin + 1)]
    return {
        "last_value": [last] * horizon,
        "seasonal_naive": [last_season[i % season] for i in range(horizon)],
    }


def analyze(prices, cutoff, months_per_period):
    season = 12 // months_per_period
    horizon = 3 * season
    origin = cutoff - horizon
    required = set(range(origin - season + 1, cutoff + 1))
    scores, forecasts, skipped = [], [], []
    for county, series in sorted(prices.items()):
        missing = required - series.keys()
        if missing:
            skipped.append((county, len(missing), period_date(min(missing), months_per_period)))
            continue

        actuals = [series[i] for i in range(origin + 1, cutoff + 1)]
        for model, predicted in baselines(series, origin, season, horizon).items():
            errors = [value - actual for value, actual in zip(predicted, actuals)]
            mae = sum(abs(error) for error in errors) / horizon
            rmse = math.sqrt(sum(error**2 for error in errors) / horizon)
            scores.append((
                county, model, period_date(origin + 1, months_per_period),
                period_date(cutoff, months_per_period), horizon, round(mae, 2), round(rmse, 2),
            ))
        for model, predicted in baselines(series, cutoff, season, horizon).items():
            for step, value in enumerate(predicted, 1):
                forecasts.append((
                    county, model, period_date(cutoff + step, months_per_period),
                    step, round(value, 2),
                ))
    return scores, forecasts, skipped


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(columns)
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path, help="Bảng tổng hợp theo tháng hoặc quý.")
    parser.add_argument("--period", choices=("month", "quarter"), required=True)
    parser.add_argument("--through", type=date.fromisoformat, required=True,
                        help="Ngày bắt đầu kỳ cuối đã kiểm tra, dạng YYYY-MM-DD.")
    parser.add_argument("--output", type=Path, required=True, help="Thư mục đầu ra mới.")
    args = parser.parse_args()
    months_per_period = 1 if args.period == "month" else 3
    cutoff = period_number(args.through, months_per_period)
    if period_date(cutoff, months_per_period) != args.through:
        parser.error("--through phải là ngày đầu tháng hoặc quý tương ứng.")

    prices = read_prices(args.summary, months_per_period, cutoff)
    scores, forecasts, skipped = analyze(prices, cutoff, months_per_period)
    args.output.mkdir(parents=True, exist_ok=False)
    write_csv(
        args.output / "backtest.csv",
        ("county", "model", "test_start", "test_end", "test_periods", "mae_eur", "rmse_eur"),
        scores,
    )
    write_csv(
        args.output / "forecasts.csv",
        ("county", "model", "period_start", "step", "forecast_median_eur"),
        forecasts,
    )
    write_csv(
        args.output / "skipped_counties.csv",
        ("county", "missing_or_low_count_periods", "first_missing_period"),
        skipped,
    )
    print(f"Có dự báo cho {len(scores) // 2} County. Bỏ qua {len(skipped)} County.")


if __name__ == "__main__":
    main()
