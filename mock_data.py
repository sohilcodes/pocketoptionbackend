import random
import time
import math

PAIRS = ["CHF/JPY", "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "EUR/GBP"]

BASE_PRICES = {
    "CHF/JPY": 170.50,
    "EUR/USD": 1.0850,
    "GBP/USD": 1.2650,
    "USD/JPY": 149.80,
    "AUD/USD": 0.6520,
    "EUR/GBP": 0.8580,
}

_candle_store = {pair: [] for pair in PAIRS}
_price_store = {pair: BASE_PRICES[pair] for pair in PAIRS}


def generate_candle(pair: str) -> dict:
    base = _price_store[pair]
    volatility = base * 0.0008

    open_price = base + random.uniform(-volatility, volatility)
    close_price = open_price + random.uniform(-volatility * 2, volatility * 2)
    high_price = max(open_price, close_price) + random.uniform(0, volatility)
    low_price = min(open_price, close_price) - random.uniform(0, volatility)

    _price_store[pair] = close_price

    return {
        "open": round(open_price, 5),
        "high": round(high_price, 5),
        "low": round(low_price, 5),
        "close": round(close_price, 5),
        "volume": random.randint(100, 1000),
        "timestamp": int(time.time()),
    }


def get_mock_candles(pair: str, count: int = 60) -> list:
    if len(_candle_store[pair]) < count:
        base = BASE_PRICES[pair]
        candles = []
        price = base * 0.995
        for i in range(count):
            volatility = base * 0.0008
            open_p = price
            close_p = price + random.uniform(-volatility * 2, volatility * 2)
            # Add slight trend
            close_p += math.sin(i / 10) * volatility
            high_p = max(open_p, close_p) + random.uniform(0, volatility)
            low_p = min(open_p, close_p) - random.uniform(0, volatility)
            candles.append({
                "open": round(open_p, 5),
                "high": round(high_p, 5),
                "low": round(low_p, 5),
                "close": round(close_p, 5),
                "volume": random.randint(100, 1000),
                "timestamp": int(time.time()) - (count - i) * 60,
            })
            price = close_p
        _candle_store[pair] = candles

    return _candle_store[pair]


def add_new_candle(pair: str):
    candle = generate_candle(pair)
    _candle_store[pair].append(candle)
    if len(_candle_store[pair]) > 200:
        _candle_store[pair].pop(0)
    return candle
