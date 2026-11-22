"""Chọn mô hình theo kiểm định cuốn chiếu và dự báo giá trung vị theo quý."""

from math import exp, log, sqrt
from statistics import mean, quantiles

from du_bao_co_so import baselines


HORIZON = 12
TREND_WINDOW = 20
MIN_TRANSACTIONS = 30
MODEL_NAMES = {
    "last_value": "Giữ giá kỳ gần nhất",
    "seasonal_naive": "Lặp lại cùng kỳ",
    "damped_trend": "Xu hướng log có giảm tốc",
}


def predict(series, origin):
    results = baselines(series, origin, 4, HORIZON)
    prices = [log(series[q]) for q in range(origin - TREND_WINDOW + 1, origin + 1)]
    center = (TREND_WINDOW - 1) / 2
    slope = sum((i - center) * value for i, value in enumerate(prices)) / sum(
        (i - center) ** 2 for i in range(TREND_WINDOW)
    )
    # Neo tại trung bình log của bốn quý mới nhất, đặt tại giữa cửa sổ đó.
    level = mean(prices[-4:]) + 1.5 * slope
    damping = 0.85
    results["damped_trend"] = [
        exp(level + slope * damping * (1 - damping ** step) / (1 - damping))
        for step in range(1, HORIZON + 1)
    ]
    return results


def price_with_band(value, offsets):
    lower, upper = offsets
    return [round(value, 2), round(max(0, value + lower), 2), round(value + upper, 2)]


def forecast_county(history, cutoff):
    series = {
        q: median for q, (median, transactions) in history.items()
        if q <= cutoff and transactions >= MIN_TRANSACTIONS
    }
    holdout_origin = cutoff - HORIZON
    final_window = range(holdout_origin - TREND_WINDOW + 1, cutoff + 1)
    if any(q not in series for q in final_window):
        return None

    origins = [
        origin for origin in range(min(series) + TREND_WINDOW - 1, holdout_origin - HORIZON + 1)
        if all(q in series for q in range(origin - TREND_WINDOW + 1, origin + HORIZON + 1))
    ]
    if len(origins) < 5:
        return None

    residuals = {model: [[] for _ in range(HORIZON)] for model in MODEL_NAMES}
    for origin in origins:
        for model, forecast in predict(series, origin).items():
            for index, price in enumerate(forecast):
                residuals[model][index].append(series[origin + index + 1] - price)

    development = {
        model: mean(abs(error) for step in errors for error in step)
        for model, errors in residuals.items()
    }
    chosen = min(development, key=development.get)
    holdout = {}
    holdout_actual = [series[q] for q in range(holdout_origin + 1, cutoff + 1)]
    holdout_predictions = predict(series, holdout_origin)
    for model, forecast in holdout_predictions.items():
        errors = [actual - value for actual, value in zip(holdout_actual, forecast)]
        holdout[model] = [round(mean(map(abs, errors)), 2), round(sqrt(mean(e**2 for e in errors)), 2)]

    offsets = []
    for errors in residuals[chosen]:
        # Khoảng sai số thực nghiệm theo bước. Bao gồm đường điểm ngay cả khi sai lệch một phía.
        cuts = quantiles(errors, n=10, method="inclusive")
        offsets.append((min(0, cuts[0]), max(0, cuts[-1])))
    future = predict(series, cutoff)[chosen]
    fixed = holdout_predictions[chosen]
    rolling = [predict(series, q - 1)[chosen][0] for q in range(holdout_origin + 1, cutoff + 1)]

    return {
        "model": chosen,
        "points": [price_with_band(value, band) for value, band in zip(future, offsets)],
        "development": {model: round(score, 2) for model, score in development.items()},
        "holdout": holdout,
        "holdoutPoints": [
            [actual, round(value, 2)]
            for actual, value in zip(holdout_actual, fixed)
        ],
        "holdoutBand": [price_with_band(value, band)[1:] for value, band in zip(fixed, offsets)],
        "rollingPoints": [round(value, 2) for value in rolling],
        "rollingBand": [price_with_band(value, offsets[0])[1:] for value in rolling],
        "origins": len(origins),
    }
