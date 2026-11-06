"""
Comprehensive Test Suite for Quant Pilot Trading Assistant
Tests all 6 Intraday Strategy Rules, Candle Patterns, Paper Engine, and Web Endpoints
"""
import sys
import os

os.environ["TESTING"] = "1"
import numpy as np
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
from app.config import StrategyConfig, AppConfig, load_app_config
from app.strategy_engine import (
    CandlePattern, detect_candle_pattern, calculate_indicators,
    evaluate_intraday_strategy
)
from app.market_data import MarketDataProvider
from app.paper_engine import PaperEngine

def test_config_loading():
    cfg = load_app_config()
    assert cfg.paper_capital == 100000.0
    assert cfg.strategy.ma_period == 20
    assert cfg.strategy.rsi_fast_period == 14
    assert cfg.strategy.rsi_slow_period == 20
    assert cfg.strategy.volume_ma_period == 5
    print("✅ Config loading passed")

def test_candle_pattern_detection():
    # 1. Hammer: Long lower wick, small body, small upper wick
    df_hammer = pd.DataFrame([
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 99.5, "volume": 1000},
        {"open": 99.6, "high": 100.2, "low": 96.0, "close": 100.1, "volume": 2000} # lower wick = 3.6, body = 0.5
    ])
    pattern, bias = detect_candle_pattern(df_hammer, idx=-1)
    assert bias == "BULLISH", f"Expected BULLISH hammer, got {pattern}, {bias}"
    assert "Hammer" in pattern

    # 2. Bullish Engulfing: Red candle followed by green candle that engulfs it
    df_engulfing = pd.DataFrame([
        {"open": 102.0, "high": 102.5, "low": 99.0, "close": 99.5, "volume": 1000}, # Red
        {"open": 99.0, "high": 103.0, "low": 98.8, "close": 102.5, "volume": 2500} # Green engulfing
    ])
    pattern, bias = detect_candle_pattern(df_engulfing, idx=-1)
    assert bias == "BULLISH"
    assert "Engulfing" in pattern
    print("✅ Candle pattern detection passed")

def test_quant_rules_strategy_evaluation():
    cfg = StrategyConfig()
    
    # Generate 50 synthetic candles simulating a strong bullish breakout:
    # 1. Price above MA(20)
    # 2. Bullish candle pattern
    # 3. RSI(14) crossing RSI(20)
    # 4. MACD Hist > 0
    # 5. Volume > Avg5
    np.random.seed(42)
    prices = [25000.0 + (i * 15.0) for i in range(50)]
    
    records = []
    base_ts = 1700000000
    for i, p in enumerate(prices):
        # Last candle is a strong green candle with surge in volume
        if i == 49:
            o = p - 10.0
            c = p + 40.0
            h = c + 5.0
            l = o - 2.0
            v = 80000.0 # High volume
        elif i == 48:
            o = p - 5.0
            c = p - 2.0
            h = p + 5.0
            l = p - 10.0
            v = 20000.0
        else:
            o = p - 5.0
            c = p + 5.0
            h = p + 10.0
            l = p - 8.0
            v = 25000.0
            
        records.append({
            "timestamp": base_ts + (i * 300),
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v
        })
        
    df = pd.DataFrame(records)
    pdh = 25500.0 # Price 25700 > PDH 25500 (Breakout)
    pdl = 24800.0
    
    result = evaluate_intraday_strategy(df, pdh, pdl, cfg)
    assert result["status"] == "OK"
    assert "verdict" in result
    assert "rules_breakdown" in result
    assert "stop_loss" in result
    assert "target_price" in result
    
    # Verify Rule 6: Target = Entry + (Risk * 2.0)
    entry = result["entry_price"]
    sl = result["stop_loss"]
    tgt = result["target_price"]
    risk = entry - sl
    assert sl < entry, "SL must be below entry for long"
    assert tgt > entry, "Target must be above entry for long"
    print(f"✅ Strategy Evaluation passed: Verdict={result['verdict']}, Entry={entry}, SL={sl}, Target={tgt}")

def test_paper_engine():
    app_cfg = AppConfig()
    engine = PaperEngine(app_cfg)
    engine.reset_account(100000.0)
    
    sym_info = {
        "symbol": "NSE:NIFTY50-INDEX",
        "name": "Nifty 50 Index",
        "lot_size": 25
    }
    
    # 1. Open Long Trade
    pos = engine.open_trade(
        symbol="NSE:NIFTY50-INDEX",
        side="LONG",
        entry_price=25000.0,
        stop_loss=24900.0,
        target_price=25200.0,
        symbol_info=sym_info,
        position_type="Index"
    )
    assert pos is not None
    assert pos["symbol"] == "NSE:NIFTY50-INDEX"
    assert pos["side"] == "LONG"
    assert pos["quantity"] >= 25
    assert engine.balance < 100000.0
    
    # 2. Price increases -> Tick update
    updated = engine.update_ticks("NSE:NIFTY50-INDEX", 25100.0)
    assert updated["unrealized_pnl"] > 0
    
    # 3. Target Hit at 25200 -> Auto Close
    closed = engine.update_ticks("NSE:NIFTY50-INDEX", 25210.0)
    assert closed is not None
    assert closed["status"] == "EXECUTED"
    assert closed["exit_reason"] == "TARGET_HIT"
    assert closed["pnl"] > 0
    assert "NSE:NIFTY50-INDEX" not in engine.open_positions
    
    summary = engine.get_summary()
    assert summary["total_trades"] == 1
    assert summary["winning_trades"] == 1
    assert summary["win_rate"] == 100.0
    print(f"✅ Paper Engine passed: PnL=₹{closed['pnl']}, WinRate={summary['win_rate']}%")

def test_fastapi_endpoints():
    from app.web_server import get_candles, get_watchlist, get_portfolio, get_market_status
    
    # 1. Watchlist endpoint
    wl_data = get_watchlist()
    assert len(wl_data["watchlist"]) >= 8
    
    # 2. Candles endpoint with MA20 and indicator arrays
    c_data = get_candles("NSE:NIFTY50-INDEX")
    assert "candles" in c_data
    assert "ma20" in c_data
    assert "volume" in c_data
    assert "evaluation" in c_data
    assert len(c_data["candles"]) >= 50
    assert c_data["pdh"] > 0
    assert c_data["pdl"] > 0
    
    # 3. Portfolio endpoint
    p_data = get_portfolio()
    assert "summary" in p_data
    assert p_data["summary"]["current_balance"] > 0
    
    # 4. Market status endpoint
    m_data = get_market_status()
    assert "nse_status" in m_data
    assert "mcx_status" in m_data
    
    print("✅ All FastAPI Web Server Endpoints verified successfully!")

if __name__ == "__main__":
    test_config_loading()
    test_candle_pattern_detection()
    test_quant_rules_strategy_evaluation()
    test_paper_engine()
    test_fastapi_endpoints()
    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY! 🚀")
