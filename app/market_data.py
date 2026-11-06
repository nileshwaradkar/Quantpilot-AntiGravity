"""
Quant Pilot - Market Data Provider
Multi-tier data engine supporting:
1. Fyers API v3 (Direct Broker Feed)
2. Free Real-time / Intraday Market Feed (Yahoo Finance REST API)
3. 24/7 Realistic Replay & Simulation Engine for offline testing & off-market hours
"""
import time
import json
import socket
import random
import requests
import datetime
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from .config import DEFAULT_WATCHLIST, AppConfig

class MarketDataProvider:
    def __init__(self, config: AppConfig):
        self.config = config
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        self._session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(max_retries=0)
        self._session.mount('https://', adapter)
        self._session.mount('http://', adapter)
        
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._simulation_states: Dict[str, Dict[str, Any]] = {}
        self._last_network_check: float = 0.0
        self._network_available: bool = False  # Checked dynamically

    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        for item in DEFAULT_WATCHLIST:
            if item["symbol"] == symbol:
                return item
        # If custom symbol
        return {
            "symbol": symbol,
            "name": symbol,
            "segment": "EQUITY",
            "yahoo_symbol": symbol.replace("NSE:", "").replace("-EQ", ".NS"),
            "lot_size": 1,
            "tick_size": 0.05,
            "strike_step": 50,
            "exchange": "NSE"
        }

    def _is_internet_reachable(self) -> bool:
        """Fast non-blocking DNS check to verify internet availability (returns in ~10ms)"""
        now = time.time()
        if now - self._last_network_check < 60.0:
            return self._network_available
        self._last_network_check = now
        try:
            socket.getaddrinfo("query1.finance.yahoo.com", 443)
            self._network_available = True
        except Exception:
            self._network_available = False
        return self._network_available

    def fetch_candles(self, symbol: str, resolution: str = "5m", count: int = 100) -> Tuple[pd.DataFrame, float, float]:
        """
        Fetches intraday OHLCV candles, and returns (df, pdh, pdl).
        Tier 1: Fyers API (if token valid)
        Tier 2: Yahoo Finance REST API (if internet reachable)
        Tier 3: Realistic Intraday Simulation Engine
        """
        info = self.get_symbol_info(symbol)
        yahoo_sym = info.get("yahoo_symbol", "^NSEI") if info else "^NSEI"
        
        # 1. Try Fyers API if credentials present and internet available
        if self._is_internet_reachable():
            if self.config.fyers_access_token and self.config.fyers_client_id:
                try:
                    df, pdh, pdl = self._fetch_fyers(symbol, resolution)
                    if df is not None and len(df) >= 30:
                        return df, pdh, pdl
                except Exception:
                    pass

            # 2. Try Yahoo Finance REST API
            try:
                df, pdh, pdl = self._fetch_yahoo(yahoo_sym, resolution)
                if df is not None and len(df) >= 30:
                    return df, pdh, pdl
            except Exception:
                pass

        # 3. Fallback to High-Fidelity Market Replay & Simulation Engine
        return self._generate_simulation_candles(symbol, info, count)

    def _fetch_fyers(self, symbol: str, resolution: str = "5") -> Tuple[Optional[pd.DataFrame], float, float]:
        """
        Fetches from Fyers API v3 history endpoint
        """
        token = self.config.fyers_access_token
        app_id = self.config.fyers_client_id
        auth_header = f"{app_id}:{token}"
        
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        five_days_ago = (datetime.datetime.now() - datetime.timedelta(days=5)).strftime("%Y-%m-%d")
        
        # 1. Fetch Daily candle for Previous Day High & Low
        daily_url = f"https://api-t1.fyers.in/data/history?symbol={symbol}&resolution=D&date_format=1&range_from={five_days_ago}&range_to={today}&cont_flag=1"
        res_d = self._session.get(daily_url, headers={"Authorization": auth_header}, timeout=1.0)
        pdh, pdl = 0.0, 0.0
        if res_d.status_code == 200:
            d_data = res_d.json()
            if d_data.get("s") == "ok" and len(d_data.get("candles", [])) >= 2:
                # Previous day is candles[-2]
                prev_day = d_data["candles"][-2]
                pdh = float(prev_day[2])
                pdl = float(prev_day[3])

        # 2. Fetch Intraday 5m Candles
        res_code = "5" if "5" in resolution else "5"
        intra_url = f"https://api-t1.fyers.in/data/history?symbol={symbol}&resolution={res_code}&date_format=1&range_from={five_days_ago}&range_to={today}&cont_flag=1"
        res_i = requests.get(intra_url, headers={"Authorization": auth_header}, timeout=6)
        if res_i.status_code == 200:
            i_data = res_i.json()
            if i_data.get("s") == "ok" and i_data.get("candles"):
                # Candle format: [epoch, open, high, low, close, volume]
                cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                df = pd.DataFrame(i_data["candles"], columns=cols)
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='s', utc=True).dt.tz_convert('Asia/Kolkata')
                return df, pdh, pdl

        return None, 0.0, 0.0

    def _fetch_yahoo(self, yahoo_symbol: str, resolution: str = "5m") -> Tuple[Optional[pd.DataFrame], float, float]:
        """
        Fetches 5-minute candles from Yahoo Finance v8 chart API
        """
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?range=5d&interval=5m"
        resp = self._session.get(url, headers=self.headers, timeout=1.0)
        if resp.status_code != 200:
            return None, 0.0, 0.0
            
        data = resp.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None, 0.0, 0.0
            
        r = result[0]
        timestamps = r.get("timestamp", [])
        quote = r.get("indicators", {}).get("quote", [{}])[0]
        
        opens = quote.get("open", [])
        highs = quote.get("high", [])
        lows = quote.get("low", [])
        closes = quote.get("close", [])
        volumes = quote.get("volume", [])
        
        records = []
        for t, o, h, l, c, v in zip(timestamps, opens, highs, lows, closes, volumes):
            if None not in (o, h, l, c):
                records.append({
                    "timestamp": t,
                    "open": float(o),
                    "high": float(h),
                    "low": float(l),
                    "close": float(c),
                    "volume": float(v or 1000)
                })
                
        if not records:
            return None, 0.0, 0.0
            
        df = pd.DataFrame(records)
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s', utc=True).dt.tz_convert('Asia/Kolkata')
        
        # Calculate Previous Day High and Low from historical data
        # Group by date
        df['date'] = df['datetime'].dt.date
        unique_dates = sorted(df['date'].unique())
        
        pdh, pdl = 0.0, 0.0
        if len(unique_dates) >= 2:
            prev_date = unique_dates[-2]
            prev_day_df = df[df['date'] == prev_date]
            pdh = float(prev_day_df['high'].max())
            pdl = float(prev_day_df['low'].min())
        else:
            # Fallback approximate PDH/PDL
            pdh = float(df['high'].max() * 0.998)
            pdl = float(df['low'].min() * 1.002)

        return df, pdh, pdl

    def _generate_simulation_candles(
        self,
        symbol: str,
        info: Optional[Dict[str, Any]],
        count: int = 120
    ) -> Tuple[pd.DataFrame, float, float]:
        """
        Generates realistic intraday candle sequence matching the Indian market dynamics.
        Allows 24/7 paper trading, rule backtesting and instant UI testing on iPhone & Windows!
        """
        # Base realistic prices for Indian assets
        base_prices = {
            "NSE:NIFTY50-INDEX": 25800.0,
            "NSE:NIFTYBANK-INDEX": 54200.0,
            "NSE:FINNIFTY-INDEX": 24800.0,
            "MCX:CRUDEOILM-FUT": 6150.0,
            "NSE:HDFCBANK-EQ": 992.0,
            "NSE:RELIANCE-EQ": 1420.0,
            "NSE:TCS-EQ": 4150.0,
            "NSE:ICICIBANK-EQ": 1280.0
        }
        
        base_price = base_prices.get(symbol, 1000.0)
        
        # Check if we have an active simulation state
        if symbol not in self._simulation_states:
            # Seed state with previous day high/low
            pdh = round(base_price * 1.008, 2)
            pdl = round(base_price * 0.992, 2)
            
            # Create synthetic history leading up to now
            now_epoch = int(time.time())
            start_epoch = now_epoch - (count * 300) # 5m per candle
            
            candles = []
            curr_price = base_price * 0.995 # Start below PDH
            trend = 1 if random.random() > 0.4 else -1
            
            for i in range(count):
                ts = start_epoch + (i * 300)
                # Volatility
                volat = base_price * 0.0018
                drift = (volat * 0.15) * trend
                
                # Near recent candles, let's inject a breakout setup!
                if i > (count - 15) and trend == 1:
                    # Accelerate toward PDH
                    drift += (volat * 0.4)
                
                open_p = curr_price
                change = np.random.normal(drift, volat)
                close_p = open_p + change
                high_p = max(open_p, close_p) + abs(np.random.normal(0, volat * 0.5))
                low_p = min(open_p, close_p) - abs(np.random.normal(0, volat * 0.5))
                
                # Volume with occasional surges
                base_vol = 50000 if "INDEX" in symbol else 12000
                if i >= (count - 3):
                    volume = base_vol * random.uniform(1.6, 2.5) # Spike volume
                else:
                    volume = base_vol * random.uniform(0.6, 1.4)
                    
                candles.append({
                    "timestamp": ts,
                    "open": round(open_p, 2),
                    "high": round(high_p, 2),
                    "low": round(low_p, 2),
                    "close": round(close_p, 2),
                    "volume": round(volume, 0)
                })
                curr_price = close_p
                
            self._simulation_states[symbol] = {
                "candles": candles,
                "pdh": pdh,
                "pdl": pdl,
                "last_update": time.time(),
                "trend": trend
            }
        else:
            state = self._simulation_states[symbol]
            candles = state["candles"]
            pdh = state["pdh"]
            pdl = state["pdl"]
            
            # Periodically append new tick/candle every 5 seconds in simulation
            if time.time() - state["last_update"] >= 5.0:
                last_c = candles[-1]
                now_epoch = int(time.time())
                
                # Either update current candle or create new
                volat = base_price * 0.0015
                open_p = last_c["close"]
                close_p = open_p + np.random.normal(volat * 0.1 * state["trend"], volat * 0.6)
                high_p = max(open_p, close_p) + abs(np.random.normal(0, volat * 0.4))
                low_p = min(open_p, close_p) - abs(np.random.normal(0, volat * 0.4))
                volume = (50000 if "INDEX" in symbol else 12000) * random.uniform(1.1, 2.0)
                
                # Rotate candles
                candles.pop(0)
                candles.append({
                    "timestamp": now_epoch,
                    "open": round(open_p, 2),
                    "high": round(high_p, 2),
                    "low": round(low_p, 2),
                    "close": round(close_p, 2),
                    "volume": round(volume, 0)
                })
                state["last_update"] = time.time()

        df = pd.DataFrame(candles)
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s', utc=True).dt.tz_convert('Asia/Kolkata')
        return df, pdh, pdl

    def get_market_status(self) -> Dict[str, Any]:
        """
        Determines current market status for NSE and MCX according to IST hours.
        NSE: 9:15 AM - 3:30 PM (Mon-Fri)
        MCX: 9:00 AM - 11:30 PM (Mon-Fri)
        """
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        ist = now_utc + datetime.timedelta(hours=5, minutes=30)
        
        weekday = ist.weekday() # 0 = Monday, 6 = Sunday
        is_weekday = weekday < 5
        
        cur_time = ist.time()
        nse_open_time = datetime.time(9, 15)
        nse_close_time = datetime.time(15, 30)
        
        mcx_open_time = datetime.time(9, 0)
        mcx_close_time = datetime.time(23, 30)
        
        nse_is_open = is_weekday and (nse_open_time <= cur_time <= nse_close_time)
        mcx_is_open = is_weekday and (mcx_open_time <= cur_time <= mcx_close_time)
        
        return {
            "ist_time": ist.strftime("%Y-%m-%d %H:%M:%S IST"),
            "weekday": ist.strftime("%A"),
            "nse_status": "OPEN" if nse_is_open else "CLOSED",
            "mcx_status": "OPEN" if mcx_is_open else "CLOSED",
            "is_market_hours": nse_is_open or mcx_is_open
        }
