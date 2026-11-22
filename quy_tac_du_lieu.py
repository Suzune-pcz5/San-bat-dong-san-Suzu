"""Lược đồ và các giá trị dùng chung khi đọc Irish Property Price Register."""

import csv


INPUT_COLUMNS = (
    "date_of_sale", "address", "county", "eircode", "price_eur",
    "not_full_market_price", "vat_exclusive", "description", "property_size",
)

COUNTIES = (
    "Carlow", "Cavan", "Clare", "Cork", "Donegal", "Dublin", "Galway",
    "Kerry", "Kildare", "Kilkenny", "Laois", "Leitrim", "Limerick",
    "Longford", "Louth", "Mayo", "Meath", "Monaghan", "Offaly",
    "Roscommon", "Sligo", "Tipperary", "Waterford", "Westmeath",
    "Wexford", "Wicklow",
)

COUNTY_PREFIX = r"(?i)^co\.\s*"
PRICE_FORMAT = r"^(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]{1,2})?$"
LOW_PRICE = 10_000
HIGH_PRICE = 5_000_000
TRUE_FLAGS = ("true", "1", "yes")
FALSE_FLAGS = ("false", "0", "no")
SECOND_HAND_PATTERN = r"^second[ -]hand\b"
NEW_PATTERN = r"^new\b"
SECOND_HAND_IRISH = "teach/árasán cónaithe atháimhe"
NEW_IRISH = ("teach/árasán cónaithe nua", "teach/?ras?n c?naithe nua")


def input_header(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        header = next(csv.reader(file), [])
    if len(header) != len(INPUT_COLUMNS) or set(header) != set(INPUT_COLUMNS):
        raise ValueError(f"CSV cần đúng chín cột của nguồn Kaggle. Cột tìm thấy: {header}")
    return header
