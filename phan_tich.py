"""Làm sạch và tổng hợp giao dịch nhà ở Ireland bằng PySpark."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from pyspark.sql import SparkSession, functions as F


from quy_tac_du_lieu import (
    COUNTIES, COUNTY_PREFIX, FALSE_FLAGS, HIGH_PRICE, LOW_PRICE, NEW_IRISH,
    NEW_PATTERN, PRICE_FORMAT, SECOND_HAND_IRISH, SECOND_HAND_PATTERN,
    TRUE_FLAGS, input_header,
)


def flag(name):
    value = F.lower(F.trim(F.col(name)))
    return F.when(value.isin(*TRUE_FLAGS), True).when(
        value.isin(*FALSE_FLAGS), False
    )


def normalize(raw):
    date = F.trim("date_of_sale")
    price = F.trim(F.regexp_replace(F.trim("price_eur"), "^€", ""))
    description = F.lower(F.trim("description"))
    county = F.initcap(F.regexp_replace(F.trim("county"), COUNTY_PREFIX, ""))

    return raw.select(
        F.coalesce(
            F.try_to_timestamp(date, F.lit("yyyy-MM-dd")),
            F.try_to_timestamp(date, F.lit("d/M/yyyy")),
        ).cast("date").alias("sale_date"),
        F.when(county.isin(*COUNTIES), county).alias("county"),
        F.when(
            price.rlike(PRICE_FORMAT),
            F.regexp_replace(price, ",", "").try_cast("decimal(16,2)"),
        ).alias("price_eur"),
        flag("not_full_market_price").alias("not_full_market_price"),
        flag("vat_exclusive").alias("vat_exclusive"),
        F.when(
            description.rlike(SECOND_HAND_PATTERN) | (description == SECOND_HAND_IRISH),
            "second_hand",
        )
        .when(
            description.rlike(NEW_PATTERN) | description.isin(*NEW_IRISH),
            "new",
        )
        .alias("property_type"),
        (F.trim(F.coalesce("eircode", F.lit(""))) == "").alias("missing_eircode"),
        (F.trim(F.coalesce("property_size", F.lit(""))) == "").alias("missing_property_size"),
    )


def write_csv(frame, path):
    # Chỉ chuyển bảng tổng hợp nhỏ về Python để ghi một CSV dễ mở.
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(frame.columns)
        writer.writerows(frame.toLocalIterator())


def process(spark, source, header, destination, min_transactions):
    raw = (
        spark.read.schema(", ".join(f"{name} STRING" for name in header))
        .option("header", True)
        .option("enforceSchema", False)
        .option("escape", '"')
        .option("mode", "FAILFAST")
        .csv(source.as_posix())
    )
    normalized = normalize(raw).cache()
    invalid_date = F.col("sale_date").isNull()
    invalid_county = F.col("county").isNull()
    invalid_price = F.col("price_eur").isNull() | (F.col("price_eur") <= 0)
    valid = ~(invalid_date | invalid_county | invalid_price)
    eligible = (
        valid
        & ~F.col("not_full_market_price")
        & ~F.col("vat_exclusive")
        & F.col("property_type").isNotNull()
    )
    eligible_price = F.when(eligible, F.col("price_eur"))

    quality = normalized.agg(
        F.count("*").alias("raw_rows"),
        F.min("sale_date").alias("first_parsed_date"),
        F.max("sale_date").alias("last_parsed_date"),
        F.count_if(invalid_date).alias("invalid_date_rows"),
        F.count_if(invalid_county).alias("invalid_county_rows"),
        F.count_if(invalid_price).alias("invalid_price_rows"),
        F.count_if(F.col("missing_eircode")).alias("missing_eircode_rows"),
        F.count_if(F.col("missing_property_size")).alias("missing_property_size_rows"),
        F.count_if(F.col("not_full_market_price").isNull()).alias("unknown_market_flag_rows"),
        F.count_if(F.col("vat_exclusive").isNull()).alias("unknown_vat_flag_rows"),
        F.count_if(F.col("property_type").isNull()).alias("unknown_property_type_rows"),
        F.count_if(valid).alias("valid_rows"),
        F.count_if(F.col("not_full_market_price")).alias("non_market_price_rows"),
        F.count_if(F.col("vat_exclusive")).alias("vat_exclusive_rows"),
        F.count_if(eligible).alias("clean_rows"),
        F.min(F.when(eligible, F.col("sale_date"))).alias("clean_first_sale"),
        F.max(F.when(eligible, F.col("sale_date"))).alias("clean_last_sale"),
        F.count_if(eligible_price <= LOW_PRICE).alias("clean_price_at_or_below_low_threshold"),
        F.count_if(eligible_price >= HIGH_PRICE).alias("clean_price_at_or_above_high_threshold"),
        F.count_if(eligible & (F.col("property_type") == "new")).alias("eligible_new_rows"),
        F.count_if(eligible & (F.col("property_type") == "second_hand")).alias(
            "eligible_second_hand_rows"
        ),
    ).first().asDict()

    if quality["clean_rows"] == 0:
        raise ValueError(f"Không có giao dịch đủ điều kiện. Thống kê: {quality}")

    sales = normalized.filter(eligible)
    # Lấy hai vị trí giữa trên giá Decimal để làm tròn đúng đến cent.
    prices = F.col("sorted_prices")
    size = F.size(prices)
    lower = F.get(prices, ((size - 1) / 2).cast("int"))
    upper = F.get(prices, (size / 2).cast("int"))
    for period in ("month", "quarter"):
        summary = (
            sales.withColumn("period_start", F.date_trunc(period, "sale_date").cast("date"))
            .groupBy("county", "period_start", "property_type")
            .agg(
                F.count("*").alias("transactions"),
                F.sort_array(F.collect_list("price_eur")).alias("sorted_prices"),
                F.round(F.avg("price_eur"), 2).alias("mean_eur"),
            )
            .select(
                "county", "period_start", "property_type", "transactions",
                F.round((lower + upper) / 2, 2).alias("median_eur"),
                "mean_eur",
                (F.col("transactions") >= min_transactions).alias("meets_count_threshold"),
            )
            .orderBy("county", "period_start", "property_type")
        )
        write_csv(summary, destination / f"prices_by_{period}.csv")

    with source.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    quality.update(
        excluded_rows=quality["raw_rows"] - quality["clean_rows"],
        review_low_price_eur=LOW_PRICE,
        review_high_price_eur=HIGH_PRICE,
        source_file=source.name,
        source_sha256=digest,
        min_transactions=min_transactions,
        spark_version=spark.version,
        spark_master=spark.sparkContext.master,
    )
    (destination / "quality.json").write_text(
        json.dumps(quality, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return quality


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="CSV từ bộ Irish Property Price Register.")
    parser.add_argument("--output", required=True, type=Path, help="Thư mục kết quả mới.")
    parser.add_argument("--min-transactions", type=int, default=30)
    args = parser.parse_args()

    source = args.csv.resolve()
    output = args.output.resolve()
    if not source.is_file():
        parser.error(f"Không tìm thấy CSV: {source}")
    if output.exists():
        parser.error(f"Thư mục đầu ra đã tồn tại: {output}")
    if args.min_transactions < 1:
        parser.error("--min-transactions phải lớn hơn hoặc bằng 1.")
    header = input_header(source)

    os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")
    spark = (
        SparkSession.builder.master("local[*]")
        .appName("Nhom2IrelandPropertyPrices")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "16")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with TemporaryDirectory(dir=output.parent, prefix=".ireland-") as temp:
            staging = Path(temp) / "result"
            staging.mkdir()
            quality = process(spark, source, header, staging, args.min_transactions)
            staging.rename(output)
        print(
            f"{quality['raw_rows']:,} giao dịch đầu vào. "
            f"{quality['eligible_second_hand_rows']:,} giao dịch nhà cũ đủ điều kiện. "
            f"Kết quả: {output}"
        )
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
