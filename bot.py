import os
import time
import requests

BINANCE_URL = "https://fapi.binance.com/fapi/v1/klines"
TELEGRAM_URL = "https://api.telegram.org/bot{}/sendMessage"

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def ema(values, period):
    if len(values) < period:
        return []
    k = 2 / (period + 1)
    result = [sum(values[:period]) / period]
    for price in values[period:]:
        result.append(price * k + result[-1] * (1 - k))
    return result


def rsi(values, period=14):
    if len(values) < period + 1:
        return 50

    gains = []
    losses = []

    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(highs, lows, closes, period=14):
    trs = []

    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
        trs.append(tr)

    if len(trs) < period:
        return 0

    return sum(trs[-period:]) / period


def get_data():
    params = {
        "symbol": "ETHUSDT",
        "interval": "1m",
        "limit": 100
    }

    data = requests.get(BINANCE_URL, params=params, timeout=10).json()

    opens = [float(x[1]) for x in data]
    highs = [float(x[2]) for x in data]
    lows = [float(x[3]) for x in data]
    closes = [float(x[4]) for x in data]
    volumes = [float(x[5]) for x in data]
    times = [int(x[0]) for x in data]

    return opens, highs, lows, closes, volumes, times


def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        print("Telegram settings missing")
        return

    url = TELEGRAM_URL.format(TOKEN)

    requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message
        },
        timeout=10
    )


def make_signal():
    opens, highs, lows, closes, volumes, times = get_data()

    # Last CLOSED candle
    close = closes[-2]
    candle_time = times[-2]

    ema9 = ema(closes, 9)[-2]
    ema21 = ema(closes, 21)[-2]

    rsi_value = rsi(closes, 14)

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)

    macd_values = []

    start = 25
    for i in range(start, len(closes)):
        macd_values.append(
            ema12[i - 11] - ema26[i - 25]
        )

    signal_line = ema(macd_values, 9)

    if not signal_line:
        return None

    macd_hist = macd_values[-1] - signal_line[-1]

    atr_value = atr(highs, lows, closes, 14)

    avg_volume = sum(volumes[-22:-2]) / 20
    volume_ok = volumes[-2] > avg_volume

    long_score = 0
    short_score = 0

    if ema9 > ema21:
        long_score += 1
    else:
        short_score += 1

    if rsi_value > 50:
        long_score += 1
    elif rsi_value < 50:
        short_score += 1

    if macd_hist > 0:
        long_score += 1
    elif macd_hist < 0:
        short_score += 1

    if close > ema21:
        long_score += 1
    elif close < ema21:
        short_score += 1

    if volume_ok:
        if close > opens[-2]:
            long_score += 1
        else:
            short_score += 1

    if long_score >= 4 and long_score > short_score:
        side = "LONG"
        score = long_score
        sl = close - (1.2 * atr_value)
        tp = close + (1.5 * (close - sl))

    elif short_score >= 4 and short_score > long_score:
        side = "SHORT"
        score = short_score
        sl = close + (1.2 * atr_value)
        tp = close - (1.5 * (sl - close))

    else:
        return None

    return {
        "time": candle_time,
        "side": side,
        "score": score,
        "entry": close,
        "sl": sl,
        "tp": tp
    }


last_signal = None

while True:
    try:
        signal = make_signal()

        if signal:
            signal_id = f"{signal['time']}_{signal['side']}"

            if signal_id != last_signal:
                emoji = "📈" if signal["side"] == "LONG" else "📉"

                message = f"""🚨 ETH/USDT 1M SIGNAL

{emoji} {signal['side']}

🎯 Entry: {signal['entry']:.2f}
🛑 Stop Loss: {signal['sl']:.2f}
💰 Take Profit: {signal['tp']:.2f}

📊 Score: {signal['score']}/5

⚠️ Manual trading on Ult
⚠️ Signal is NOT guaranteed
"""

                send_telegram(message)

                print(message)
                last_signal = signal_id

        time.sleep(10)

    except Exception as e:
        print("Error:", e)
        time.sleep(10)
