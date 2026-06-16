import numpy as np
from typing import List, Dict


def calculate_ema(prices: List[float], period: int) -> List[float]:
    if len(prices) < period:
        return [prices[-1]] * len(prices) if prices else []

    ema = [0.0] * len(prices)
    multiplier = 2 / (period + 1)

    # Start with SMA
    ema[period - 1] = sum(prices[:period]) / period

    for i in range(period, len(prices)):
        ema[i] = (prices[i] - ema[i - 1]) * multiplier + ema[i - 1]

    # Fill initial values
    for i in range(period - 1):
        ema[i] = ema[period - 1]

    return ema


def calculate_rsi(prices: List[float], period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0

    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)


def detect_candle_pattern(candles: List[Dict]) -> str:
    if len(candles) < 3:
        return "NEUTRAL"

    last3 = candles[-3:]
    closes = [c["close"] for c in last3]
    opens = [c["open"] for c in last3]

    bullish_count = sum(1 for i in range(3) if closes[i] > opens[i])
    bearish_count = sum(1 for i in range(3) if closes[i] < opens[i])

    if bullish_count >= 2 and closes[-1] > closes[-2] > closes[-3]:
        return "STRONG_BULLISH"
    elif bearish_count >= 2 and closes[-1] < closes[-2] < closes[-3]:
        return "STRONG_BEARISH"
    elif bullish_count >= 2:
        return "BULLISH"
    elif bearish_count >= 2:
        return "BEARISH"
    else:
        return "NEUTRAL"


def predict_next_candle(
    candles: List[Dict],
    ema9: float,
    ema21: float,
    rsi: float,
) -> Dict:
    pattern = detect_candle_pattern(candles)
    score = 0

    # Pattern score
    if pattern == "STRONG_BULLISH":
        score += 3
    elif pattern == "BULLISH":
        score += 1
    elif pattern == "STRONG_BEARISH":
        score -= 3
    elif pattern == "BEARISH":
        score -= 1

    # EMA trend
    if ema9 > ema21:
        score += 2
    else:
        score -= 2

    # RSI momentum
    if rsi < 40:
        score += 1
    elif rsi > 60:
        score -= 1

    # Price vs EMA
    if candles:
        last_close = candles[-1]["close"]
        if last_close > ema9:
            score += 1
        else:
            score -= 1

    total_possible = 7
    abs_score = abs(score)
    confidence = min(int((abs_score / total_possible) * 100), 95)
    confidence = max(confidence, 52)

    direction = "UP" if score >= 0 else "DOWN"

    return {
        "direction": direction,
        "confidence": confidence,
        "pattern": pattern,
        "score": score,
    }


def generate_signal(
    rsi: float,
    ema9: float,
    ema21: float,
    ema50: float,
) -> Dict:
    ema_bullish = ema9 > ema21
    ema_bearish = ema9 < ema21

    if rsi < 30 and ema_bullish:
        return {"signal": "BUY", "confidence": "HIGH", "reason": "RSI oversold + EMA bullish crossover"}
    elif rsi > 70 and ema_bearish:
        return {"signal": "SELL", "confidence": "HIGH", "reason": "RSI overbought + EMA bearish crossover"}
    elif rsi < 40 and ema_bullish:
        return {"signal": "BUY", "confidence": "MEDIUM", "reason": "RSI low + EMA bullish trend"}
    elif rsi > 60 and ema_bearish:
        return {"signal": "SELL", "confidence": "MEDIUM", "reason": "RSI high + EMA bearish trend"}
    else:
        return {"signal": "WAIT", "confidence": "LOW", "reason": "No clear signal"}
