"""
Quant Pilot - Configuration & Settings
Covers Indian Markets (NSE Equity & Indices, MCX Commodities)
"""
import os
import json
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "trade_logs"
CONFIG_FILE = BASE_DIR / "config.json"

DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# Default Watchlist for Indian Markets
DEFAULT_WATCHLIST = [
    {
        "symbol": "NSE:NIFTY50-INDEX",
        "name": "Nifty 50 Index",
        "segment": "INDEX",
        "yahoo_symbol": "^NSEI",
        "lot_size": 25,
        "tick_size": 0.05,
        "strike_step": 50,
        "exchange": "NSE"
    },
    {
        "symbol": "NSE:NIFTYBANK-INDEX",
        "name": "Bank Nifty Index",
        "segment": "INDEX",
        "yahoo_symbol": "^NSEBANK",
        "lot_size": 15,
        "tick_size": 0.05,
        "strike_step": 100,
        "exchange": "NSE"
    },
    {
        "symbol": "NSE:FINNIFTY-INDEX",
        "name": "Fin Nifty Index",
        "segment": "INDEX",
        "yahoo_symbol": "NIFTY_FIN_SERVICE.NS",
        "lot_size": 25,
        "tick_size": 0.05,
        "strike_step": 50,
        "exchange": "NSE"
    },
    {
        "symbol": "MCX:CRUDEOILM-FUT",
        "name": "Crude Oil (MCX)",
        "segment": "COMMODITY",
        "yahoo_symbol": "CL=F",
        "lot_size": 10,
        "tick_size": 1.0,
        "strike_step": 50,
        "exchange": "MCX"
    },
    {
        "symbol": "NSE:HDFCBANK-EQ",
        "name": "HDFC Bank Ltd",
        "segment": "EQUITY",
        "yahoo_symbol": "HDFCBANK.NS",
        "lot_size": 1,
        "tick_size": 0.05,
        "strike_step": 10,
        "exchange": "NSE"
    },
    {
        "symbol": "NSE:RELIANCE-EQ",
        "name": "Reliance Industries",
        "segment": "EQUITY",
        "yahoo_symbol": "RELIANCE.NS",
        "lot_size": 1,
        "tick_size": 0.05,
        "strike_step": 20,
        "exchange": "NSE"
    },
    {
        "symbol": "NSE:TCS-EQ",
        "name": "Tata Consultancy Services",
        "segment": "EQUITY",
        "yahoo_symbol": "TCS.NS",
        "lot_size": 1,
        "tick_size": 0.05,
        "strike_step": 50,
        "exchange": "NSE"
    },
    {
        "symbol": "NSE:ICICIBANK-EQ",
        "name": "ICICI Bank Ltd",
        "segment": "EQUITY",
        "yahoo_symbol": "ICICIBANK.NS",
        "lot_size": 1,
        "tick_size": 0.05,
        "strike_step": 10,
        "exchange": "NSE"
    }
]

class StrategyConfig(BaseModel):
    # Rule 1: MA(20) & Candle Close
    ma_period: int = 20
    candle_above_ma_ratio: float = 0.60  # Most of candle (>60%) above/below MA20
    require_candle_pattern: bool = True   # Hammer, Engulfing, Marubozu, etc.
    
    # Rule 2: RSI(14) vs RSI(20) crossover
    rsi_fast_period: int = 14
    rsi_slow_period: int = 20
    rsi_crossover_lookback: int = 4      # Bars within which crossover must have occurred
    
    # Rule 3: MACD Green / Red
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    require_macd_growing: bool = True     # Histogram > 0 and expanding
    
    # Rule 4: Volume Confirmation
    volume_ma_period: int = 5
    volume_threshold_ratio: float = 1.0  # Vol > 1.0 * SMA(Vol, 5)
    
    # Rule 5 / Pre-condition: Previous Day High / Low Breakout
    require_pdh_pdl_break: bool = True   # Must break PDH (long) or PDL (short)
    
    # Rule 6: Stop-Loss & Risk Management
    # sl_mode options: "prev_2_candles" or "swing_low_high" or "auto_tighter"
    sl_mode: str = "prev_2_candles"
    swing_lookback: int = 5
    risk_reward_ratio: float = 2.0       # 1:2 Risk to Reward
    risk_per_trade_percent: float = 1.0  # 1% of capital per trade
    max_risk_amount: float = 2000.0      # Max ₹ loss per trade
    
    # General Intraday
    timeframe: str = "5m"                # Standard 5-minute candles
    intraday_squareoff_nse: str = "15:15" # Auto square-off at 15:15 IST
    intraday_squareoff_mcx: str = "23:15" # MCX square-off at 23:15 IST

class AppConfig(BaseModel):
    # Trading Mode
    trading_mode: str = "PAPER"          # "PAPER" or "REAL"
    paper_capital: float = 100000.0      # Initial paper trading capital ₹1,00,000
    
    # Fyers Broker Credentials
    fyers_client_id: str = ""
    fyers_secret_key: str = ""
    fyers_access_token: str = ""
    fyers_redirect_uri: str = "https://trade.fyers.in/api-login/redirect-uri/index.html"
    
    # Options Trading Preferences
    options_trading_enabled: bool = True
    option_type_preference: str = "ATM"  # "ATM", "ITM1", "OTM1"
    
    # Notifications
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    sound_alerts_enabled: bool = True
    browser_notifications: bool = True
    
    # Strategy
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)

def load_app_config() -> AppConfig:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            # Map legacy config fields if present
            if "client_id" in data and not data.get("fyers_client_id"):
                data["fyers_client_id"] = data["client_id"]
            if "secret_key" in data and not data.get("fyers_secret_key"):
                data["fyers_secret_key"] = data["secret_key"]
            if "access_token" in data and not data.get("fyers_access_token"):
                data["fyers_access_token"] = data["access_token"]
            return AppConfig.model_validate(data)
        except Exception as e:
            print(f"Error loading config.json: {e}. Using defaults.")
    return AppConfig()

def save_app_config(cfg: AppConfig):
    with open(CONFIG_FILE, "w") as f:
        f.write(cfg.model_dump_json(indent=4))
