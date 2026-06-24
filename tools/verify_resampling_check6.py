import requests
from datetime import datetime, timezone
from decimal import Decimal

# Helper to fetch klines
def fetch_klines(symbol, interval, limit=1500, end_time=None):
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    if end_time:
        params["endTime"] = end_time
        
    r = requests.get(url, params=params)
    r.raise_for_status()
    return r.json()

def main():
    print("Fetching 1m and 15m candles from Binance API for BTCUSDT perpetual...")
    
    # Let's get the last 1500 1m candles
    klines_1m_raw = fetch_klines("BTCUSDT", "1m", limit=1500)
    
    # The timestamps to fetch 15m for the exact same period
    start_time_1m = klines_1m_raw[0][0]
    end_time_1m = klines_1m_raw[-1][0]
    
    # We only want complete 15m intervals.
    klines_1m = []
    started = False
    for k in klines_1m_raw:
        dt = datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc)
        if dt.minute % 15 == 0 and dt.second == 0:
            started = True
            
        if started:
            klines_1m.append(k)
            
    # Remove trailing incomplete chunk
    remainder = len(klines_1m) % 15
    if remainder != 0:
        klines_1m = klines_1m[:-remainder]
        
    if not klines_1m:
        print("Not enough complete chunks found.")
        exit(1)
        
    start_ts = klines_1m[0][0]
    end_ts = klines_1m[-1][0]
    
    # fetch 15m
    klines_15m = fetch_klines("BTCUSDT", "15m", limit=150, end_time=end_ts + 15*60*1000)
    
    # Index 15m by open time
    official_15m = {k[0]: k for k in klines_15m}
    
    mismatches = 0
    checked = 0
    
    for i in range(0, len(klines_1m), 15):
        chunk = klines_1m[i:i+15]
        
        c_open = Decimal(chunk[0][1])
        c_high = max(Decimal(c[2]) for c in chunk)
        c_low = min(Decimal(c[3]) for c in chunk)
        c_close = Decimal(chunk[-1][4])
        c_vol = sum(Decimal(c[5]) for c in chunk)
        c_open_ts = chunk[0][0]
        c_close_ts = chunk[-1][6]
        c_trades = sum(c[8] for c in chunk)
        
        # compare with official 15m
        if c_open_ts not in official_15m:
            print(f"Missing 15m candle for timestamp {c_open_ts}")
            mismatches += 1
            continue
            
        off = official_15m[c_open_ts]
        
        o_open = Decimal(off[1])
        o_high = Decimal(off[2])
        o_low = Decimal(off[3])
        o_close = Decimal(off[4])
        # Note: volumes can have very slight floating point differences from API string representation sum if precision differs.
        # But for Crypto, volume is often a float internally in Binance. Let's check if they match closely.
        # But wait, Binance volume is provided as a string, e.g. "1.234"
        o_vol = Decimal(off[5])
        o_open_ts = off[0]
        o_close_ts = off[6]
        o_trades = off[8]
        
        if c_open != o_open:
            print(f"Mismatch open at {c_open_ts}: 1m -> {c_open}, 15m -> {o_open}")
            mismatches += 1
        if c_high != o_high:
            print(f"Mismatch high at {c_open_ts}: 1m -> {c_high}, 15m -> {o_high}")
            mismatches += 1
        if c_low != o_low:
            print(f"Mismatch low at {c_open_ts}: 1m -> {c_low}, 15m -> {o_low}")
            mismatches += 1
        if c_close != o_close:
            print(f"Mismatch close at {c_open_ts}: 1m -> {c_close}, 15m -> {o_close}")
            mismatches += 1
            
        # For volume, Binance aggregate might round differently, we can check if it's within a very tight tolerance
        # Actually, if we add decimals, it should match EXACTLY.
        diff_vol = abs(c_vol - o_vol)
        if diff_vol > Decimal("0.001"):
            print(f"Mismatch vol at {c_open_ts}: 1m -> {c_vol}, 15m -> {o_vol} (diff {diff_vol})")
            mismatches += 1
            
        if c_open_ts != o_open_ts:
            print(f"Mismatch open_ts at {c_open_ts}")
            mismatches += 1
        # Close ts for 1m is chunk[-1][6], which is typically x:14:59.999
        # Close ts for 15m should be exactly the same
        if c_close_ts != o_close_ts:
            print(f"Mismatch close_ts at {c_open_ts}: 1m -> {c_close_ts}, 15m -> {o_close_ts}")
            mismatches += 1
            
        checked += 1

    print(f"Checked {checked} candles. Mismatches: {mismatches}")
    if mismatches == 0 and checked > 0:
        print("SUCCESS: Internal resampling matches official Binance 15m candles.")
        exit(0)
    else:
        print("FAILED: Reconciliation showed mismatches.")
        exit(1)

if __name__ == "__main__":
    main()
