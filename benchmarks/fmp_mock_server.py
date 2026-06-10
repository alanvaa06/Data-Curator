"""
Local mock of the 3 FMP market-data endpoints, with configurable artificial latency.

Serves deterministic per-symbol OHLC JSON shaped exactly like FMP's
historical-price-eod endpoints, so the full Data Curator production path
(transport, retry, JSON parse, entities, column builder, output) runs unmodified.
"""
import datetime
import hashlib
import json
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse


def generate_market_rows(symbol, start_date, end_date, *, adjusted_keys):
    """Deterministic weekday OHLC rows in descending date order (like FMP)."""
    seed = int(hashlib.md5(symbol.encode()).hexdigest()[:8], 16)
    base_price = 50 + (seed % 200)
    rows = []
    current = end_date
    day_index = 0
    while current >= start_date:
        if current.weekday() < 5:
            price = base_price * (1 + 0.001 * ((seed + day_index) % 21 - 10))
            low = round(price * 0.99, 2)
            high = round(price * 1.01, 2)
            open_price = round(price * 0.995, 2)
            close_price = round(price * 1.005, 2)
            volume = 1_000_000 + (seed + day_index) % 500_000
            if adjusted_keys:
                rows.append({
                    'symbol': symbol,
                    'date': current.isoformat(),
                    'adjOpen': open_price,
                    'adjHigh': high,
                    'adjLow': low,
                    'adjClose': close_price,
                    'volume': volume,
                })
            else:
                rows.append({
                    'symbol': symbol,
                    'date': current.isoformat(),
                    'open': open_price,
                    'high': high,
                    'low': low,
                    'close': close_price,
                    'volume': volume,
                    'vwap': round(price, 2),
                })
            day_index += 1
        current -= datetime.timedelta(days=1)
    return rows


class MockFmpHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'   # keep-alive support, so pooling is measurable
    latency_seconds = 0.075         # simulated WAN round-trip

    def do_GET(self):
        time.sleep(self.latency_seconds)
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        symbol = query.get('symbol', ['UNKNOWN'])[0]
        start = datetime.date.fromisoformat(query.get('from', ['2024-01-01'])[0])
        end = datetime.date.fromisoformat(query.get('to', ['2024-12-31'])[0])
        if 'historical-price-eod/full' in parsed.path:
            rows = generate_market_rows(symbol, start, end, adjusted_keys=False)
        elif 'historical-price-eod' in parsed.path:
            rows = generate_market_rows(symbol, start, end, adjusted_keys=True)
        else:
            rows = []
        body = json.dumps(rows).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass
