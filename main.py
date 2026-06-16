import asyncio
import json
import os
import time
import random
from typing import Dict, List, Set
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from indicators import calculate_ema, calculate_rsi, predict_next_candle, generate_signal
from mock_data import PAIRS, get_mock_candles, add_new_candle, _price_store, BASE_PRICES

load_dotenv()

SSID = os.getenv("POCKET_OPTION_SSID", "")
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "*")
USE_MOCK = not bool(SSID) or SSID == "your_ssid_here"

# Store for live data
candle_store: Dict[str, List[Dict]] = {}
signal_store: Dict[str, Dict] = {}
connected_clients: Set[WebSocket] = set()

PAIR_FLAGS = {
    "CHF/JPY": "🇨🇭🇯🇵",
    "EUR/USD": "🇪🇺🇺🇸",
    "GBP/USD": "🇬🇧🇺🇸",
    "USD/JPY": "🇺🇸🇯🇵",
    "AUD/USD": "🇦🇺🇺🇸",
    "EUR/GBP": "🇪🇺🇬🇧",
}


def compute_signal_for_pair(pair: str) -> Dict:
    candles = candle_store.get(pair, [])
    if len(candles) < 21:
        candles = get_mock_candles(pair, 60)
        candle_store[pair] = candles

    closes = [c["close"] for c in candles]
    current_price = closes[-1] if closes else BASE_PRICES.get(pair, 1.0)
    prev_price = closes[-2] if len(closes) > 1 else current_price
    price_change_pct = ((current_price - prev_price) / prev_price * 100) if prev_price else 0

    ema9_list = calculate_ema(closes, 9)
    ema21_list = calculate_ema(closes, 21)
    ema50_list = calculate_ema(closes, 50)

    ema9 = ema9_list[-1] if ema9_list else current_price
    ema21 = ema21_list[-1] if ema21_list else current_price
    ema50 = ema50_list[-1] if ema50_list else current_price

    rsi = calculate_rsi(closes)
    signal_data = generate_signal(rsi, ema9, ema21, ema50)
    prediction = predict_next_candle(candles, ema9, ema21, rsi)

    # EMA crossover status
    prev_ema9 = ema9_list[-2] if len(ema9_list) > 1 else ema9
    prev_ema21 = ema21_list[-2] if len(ema21_list) > 1 else ema21

    if prev_ema9 <= prev_ema21 and ema9 > ema21:
        crossover_status = "GOLDEN_CROSS"
    elif prev_ema9 >= prev_ema21 and ema9 < ema21:
        crossover_status = "DEATH_CROSS"
    elif ema9 > ema21:
        crossover_status = "BULLISH"
    else:
        crossover_status = "BEARISH"

    # Entry timer — next minute boundary
    now = int(time.time())
    seconds_in_minute = now % 60
    entry_timer = max(60 - seconds_in_minute, 5)

    # Sparkline last 20 closes
    sparkline = closes[-20:] if len(closes) >= 20 else closes

    return {
        "pair": pair,
        "flags": PAIR_FLAGS.get(pair, ""),
        "price": round(current_price, 5),
        "price_change_pct": round(price_change_pct, 3),
        "signal": signal_data["signal"],
        "confidence": signal_data["confidence"],
        "reason": signal_data["reason"],
        "prediction": prediction,
        "entry_timer": entry_timer,
        "rsi": rsi,
        "ema9": round(ema9, 5),
        "ema21": round(ema21, 5),
        "ema50": round(ema50, 5),
        "crossover_status": crossover_status,
        "sparkline": [round(p, 5) for p in sparkline],
        "candles": [
            {
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "timestamp": c["timestamp"],
            }
            for c in candles[-50:]
        ],
        "is_demo": USE_MOCK,
        "last_updated": int(time.time()),
    }


async def fetch_live_data():
    """Try to use BinaryOptionsTools v2, fallback to mock"""
    if USE_MOCK:
        return False

    try:
        from binaryoptionstoolsv2.platforms.pocketoption import PocketOptionAsync

        async with PocketOptionAsync(SSID) as client:
            for pair in PAIRS:
                try:
                    symbol = pair.replace("/", "")
                    raw_candles = await client.get_candles(symbol, 60, 60)
                    formatted = []
                    for c in raw_candles:
                        formatted.append({
                            "open": float(c.get("open", 0)),
                            "high": float(c.get("high", 0)),
                            "low": float(c.get("low", 0)),
                            "close": float(c.get("close", 0)),
                            "volume": int(c.get("volume", 0)),
                            "timestamp": int(c.get("time", time.time())),
                        })
                    if formatted:
                        candle_store[pair] = formatted
                except Exception as e:
                    print(f"Error fetching {pair}: {e}")
        return True
    except Exception as e:
        print(f"BinaryOptionsTools error: {e}. Falling back to mock data.")
        return False


async def update_all_signals():
    for pair in PAIRS:
        try:
            signal_store[pair] = compute_signal_for_pair(pair)
        except Exception as e:
            print(f"Signal error for {pair}: {e}")


async def broadcast_signals():
    if not connected_clients:
        return
    data = {
        "type": "signals_update",
        "data": list(signal_store.values()),
        "timestamp": int(time.time()),
    }
    msg = json.dumps(data)
    dead = set()
    for ws in connected_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    for ws in dead:
        connected_clients.discard(ws)


async def background_loop():
    """Main background task — update every 10s"""
    # Initialize mock data
    for pair in PAIRS:
        candle_store[pair] = get_mock_candles(pair, 60)

    await update_all_signals()

    tick = 0
    while True:
        await asyncio.sleep(10)
        tick += 1

        # Add new mock candles every minute (every 6 ticks)
        if USE_MOCK and tick % 6 == 0:
            for pair in PAIRS:
                add_new_candle(pair)
        elif not USE_MOCK and tick % 6 == 0:
            await fetch_live_data()

        await update_all_signals()
        await broadcast_signals()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(background_loop())
    yield
    task.cancel()


app = FastAPI(title="Trading Signals API", lifespan=lifespan)

origins = ["*"] if ALLOWED_ORIGIN == "*" else [ALLOWED_ORIGIN, "http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "status": "running",
        "mode": "DEMO" if USE_MOCK else "LIVE",
        "pairs": PAIRS,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": int(time.time())}


@app.get("/api/signals")
async def get_all_signals():
    if not signal_store:
        await update_all_signals()
    return {
        "status": "ok",
        "mode": "DEMO" if USE_MOCK else "LIVE",
        "count": len(signal_store),
        "signals": list(signal_store.values()),
        "timestamp": int(time.time()),
    }


@app.get("/api/signals/{pair_encoded}")
async def get_signal_by_pair(pair_encoded: str):
    pair = pair_encoded.replace("-", "/").upper()
    if pair not in PAIRS:
        return {"error": f"Pair {pair} not found", "available": PAIRS}

    if pair not in signal_store:
        signal_store[pair] = compute_signal_for_pair(pair)

    return {"status": "ok", "signal": signal_store[pair]}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    print(f"Client connected. Total: {len(connected_clients)}")

    try:
        # Send current signals immediately
        initial = {
            "type": "signals_update",
            "data": list(signal_store.values()),
            "timestamp": int(time.time()),
        }
        await websocket.send_text(json.dumps(initial))

        # Keep alive — listen for pings
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if msg == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "heartbeat"}))

    except WebSocketDisconnect:
        connected_clients.discard(websocket)
        print(f"Client disconnected. Total: {len(connected_clients)}")
    except Exception as e:
        connected_clients.discard(websocket)
        print(f"WebSocket error: {e}")
