"""Tạo dashboard Grafana có dữ liệu tổng hợp từ lượt chạy."""

import json
from datetime import datetime, timedelta, timezone


DATASOURCE = {"type": "testdata", "uid": "${DS_IRELAND}"}


def quarter_start(label):
    year, quarter = label.split("-Q")
    return datetime(int(year), (int(quarter) - 1) * 3 + 1, 1, tzinfo=timezone.utc)


def field(name, kind, values):
    return {"name": name, "type": kind, "values": values}


def panel(panel_id, title, kind, y, fields, defaults):
    return {
        "id": panel_id, "title": title, "type": kind,
        "datasource": DATASOURCE,
        "gridPos": {"x": 0, "y": y, "w": 24, "h": 12},
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "targets": [{
            "refId": "A", "scenarioId": "raw_frame", "datasource": DATASOURCE,
            "rawFrameContent": json.dumps([{"fields": fields}], ensure_ascii=False),
        }],
    }


def build_dashboard(payload):
    dates = [quarter_start(label) for label in payload["periods"]]
    length = payload["historyLength"]
    horizon = payload["horizon"]
    by_county = payload["counties"]
    featured = sorted(by_county, key=lambda name: (name not in ("Dublin", "Cork"), name))[:2]
    series = [field("Quý", "time", [int(date.timestamp() * 1000) for date in dates])]
    for county in featured:
        data = by_county[county]
        actual = [point[0] if point else None for point in data["observed"]]
        series.append(field(f"{county} · Quan sát", "number", actual + [None] * horizon))
        if data["forecast"]:
            future = [point[0] for point in data["forecast"]["points"]]
            series.append(field(f"{county} · Dự báo", "number", [None] * length + future))

    trace = panel(1, "Giá trung vị theo quý", "timeseries", 0, series,
                  {"unit": "currencyEUR", "custom": {"drawStyle": "line", "showPoints": "never"}})
    trace["fieldConfig"]["overrides"].append({
        "matcher": {"id": "byRegexp", "options": "/Dự báo$/"},
        "properties": [{"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [8, 4]}}],
    })

    current = [data["observed"][-1] or [None, None] for data in by_county.values()]
    final = [
        data["forecast"]["points"][-1][0] if data["forecast"] else None
        for data in by_county.values()
    ]
    market = panel(2, f"Giá và giao dịch theo County tại {payload['periods'][length - 1]}",
                   "table", 12, [
        field("County", "string", list(by_county)),
        field("Trung vị (EUR)", "number", [point[0] for point in current]),
        field("Giao dịch", "number", [point[1] for point in current]),
        field(f"Dự báo {payload['periods'][-1]} (EUR)", "number", final),
    ], {})
    return {
        "__inputs": [{
            "name": "DS_IRELAND", "label": "TestData cho snapshot Ireland",
            "type": "datasource", "pluginId": "testdata", "pluginName": "TestData",
        }],
        "uid": "ireland-housing-nhom2",
        "title": "Giá nhà Ireland · Nhóm 2",
        "description": "Dữ liệu thực nghiệm theo lô, được nhúng từ kết quả PySpark và Python.",
        "schemaVersion": 39,
        "timezone": "utc",
        "time": {"from": dates[0].isoformat(), "to": (dates[-1] + timedelta(days=30)).isoformat()},
        "panels": [trace, market],
    }
