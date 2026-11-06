"""
Quant Pilot - Strategy Engine
Implements all 6 Intraday Quant Rules:
  Pre-condition: Previous Day High (PDH) / Low (PDL) Breakout
  Rule 1: Green/Red candle closes on MA(20) line (>60% body/range above/below) + Candle Pattern
  Rule 2: RSI(14) crossing RSI(20) from downward to upward (or upward to downward)
  Rule 3: MACD green (Histogram > 0 and expanding) / red
  Rule 4: Volume of current candle > average volume of the last 5 candles
  Rule 6: Stop-loss: previous 2 candles low/high or swing low/high, with Risk-Reward Target
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from .config import StrategyConfig

class CandlePattern:
    HAMMER = "Hammer (Bullish Reversal)"
    BULLISH_ENGULFING = "Bullish Engulfing"
    BULLISH_MARUBOZU = "Bullish Marubozu (Strong Momentum)"
    STRONG_BULLISH = "Strong Bullish Bar"
    
    SHOOTING_STAR = "Shooting Star (Bearish Reversal)"
    BEARISH_ENGULFING = "Bearish Engulfing"
    BEARISH_MARUBOZU = "Bearish Marubozu (Strong Selling)"
    STRONG_BEARISH = "Strong Bearish Bar"
    
    NEUTRAL = "Neutral / Indecisive"

def detect_candle_pattern(df: pd.DataFrame, idx: int = -1) -> Tuple[str, str]:
    """
    Detects candle pattern at given index.
    Returns (pattern_name, bias: "BULLISH" | "BEARISH" | "NEUTRAL")
    """
    if len(df) < 2:
        return (CandlePattern.NEUTRAL, "NEUTRAL")
    
    curr = df.iloc[idx]
    prev = df.iloc[idx - 1]
    
    o, h, l, c = curr['open'], curr['high'], curr['low'], curr['close']
    po, ph, pl, pc = prev['open'], prev['high'], prev['low'], prev['close']
    
    body = abs(c - o)
    total_range = h - l if (h - l) > 0 else 0.0001
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    
    is_green = c > o
    is_red = c < o
    
    # 1. Hammer (Bullish Reversal)
    # Lower wick at least 2x body, upper wick very small, occurs after down or at support
    if is_green and lower_wick >= (1.8 * body) and upper_wick <= (0.35 * total_range) and body > 0:
        return (CandlePattern.HAMMER, "BULLISH")
    
    # 2. Bullish Engulfing
    # Prior candle red, current green completely engulfs prior candle body
    if is_green and (pc < po) and (c >= po) and (o <= pc):
        return (CandlePattern.BULLISH_ENGULFING, "BULLISH")
    
    # 3. Bullish Marubozu
    # Solid green body with almost no wicks (< 10% each)
    if is_green and (body / total_range >= 0.85):
        return (CandlePattern.BULLISH_MARUBOZU, "BULLISH")
    
    # 4. Shooting Star (Bearish Reversal)
    # Upper wick at least 2x body, lower wick small
    if is_red and upper_wick >= (1.8 * body) and lower_wick <= (0.35 * total_range) and body > 0:
        return (CandlePattern.SHOOTING_STAR, "BEARISH")
    
    # 5. Bearish Engulfing
    # Prior green, current red engulfs prior
    if is_red and (pc > po) and (c <= po) and (o >= pc):
        return (CandlePattern.BEARISH_ENGULFING, "BEARISH")
        
    # 6. Bearish Marubozu
    if is_red and (body / total_range >= 0.85):
        return (CandlePattern.BEARISH_MARUBOZU, "BEARISH")
        
    # 7. Strong Bullish / Strong Bearish bar (Body >= 60% of candle range)
    if is_green and (body / total_range >= 0.60):
        return (CandlePattern.STRONG_BULLISH, "BULLISH")
        
    if is_red and (body / total_range >= 0.60):
        return (CandlePattern.STRONG_BEARISH, "BEARISH")
        
    return (CandlePattern.NEUTRAL, "NEUTRAL")

def calculate_indicators(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    """
    Computes MA(20), RSI(14), RSI(20), MACD(12,26,9), and Volume SMA(5).
    """
    df = df.copy()
    
    # MA(20)
    df['ma20'] = df['close'].rolling(window=cfg.ma_period, min_periods=1).mean()
    
    # RSI (Wilder's Smoothing)
    for length, col in [(cfg.rsi_fast_period, 'rsi_fast'), (cfg.rsi_slow_period, 'rsi_slow')]:
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        
        # Exponential smoothing (RMA)
        alpha = 1.0 / length
        avg_gain = gain.ewm(alpha=alpha, adjust=False).mean()
        avg_loss = loss.ewm(alpha=alpha, adjust=False).mean()
        
        rs = avg_gain / avg_loss.replace(0, 1e-9)
        df[col] = 100 - (100 / (1 + rs))
        df[col] = df[col].fillna(50.0)
    
    # MACD (12, 26, 9)
    fast_ema = df['close'].ewm(span=cfg.macd_fast, adjust=False).mean()
    slow_ema = df['close'].ewm(span=cfg.macd_slow, adjust=False).mean()
    df['macd_line'] = fast_ema - slow_ema
    df['macd_signal'] = df['macd_line'].ewm(span=cfg.macd_signal, adjust=False).mean()
    df['macd_hist'] = df['macd_line'] - df['macd_signal']
    
    # Volume SMA(5)
    df['vol_ma5'] = df['volume'].rolling(window=cfg.volume_ma_period, min_periods=1).mean()
    
    return df

def evaluate_intraday_strategy(
    df: pd.DataFrame,
    pdh: float,
    pdl: float,
    cfg: StrategyConfig
) -> Dict[str, Any]:
    """
    Evaluates all 6 Intraday Quant Rules on the latest candle.
    Returns comprehensive evaluation dictionary.
    """
    if len(df) < max(cfg.ma_period, cfg.rsi_slow_period, cfg.macd_slow) + 5:
        return {
            "status": "INSUFFICIENT_DATA",
            "message": f"Requires at least {cfg.rsi_slow_period + 10} candles, got {len(df)}",
            "rules": {},
            "verdict": "HOLD"
        }
    
    df = calculate_indicators(df, cfg)
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    c_open = float(curr['open'])
    c_high = float(curr['high'])
    c_low = float(curr['low'])
    c_close = float(curr['close'])
    c_vol = float(curr['volume'])
    c_ma20 = float(curr['ma20'])
    
    # Pre-condition: Price breaks Previous Day High (for Longs) or Low (for Shorts)
    # Price breaks means high > pdh or current close > pdh (for long)
    # low < pdl or current close < pdl (for short)
    pdh_broken = bool(c_high > pdh or c_close > pdh) if pdh > 0 else True
    pdl_broken = bool(c_low < pdl or c_close < pdl) if pdl > 0 else True
    
    # -------------------------------------------------------------
    # RULE 1: Green candle closes on MA(20) line
    # - Most of the candle should be above MA(20) line
    # - Consider candle type (Hammer, Engulfing, etc.)
    # -------------------------------------------------------------
    is_green = bool(c_close > c_open)
    is_red = bool(c_close < c_open)
    
    candle_height = max(c_high - c_low, 0.0001)
    # Portion above MA20:
    if c_ma20 <= c_low:
        above_ratio = 1.0
    elif c_ma20 >= c_high:
        above_ratio = 0.0
    else:
        above_ratio = (c_high - c_ma20) / candle_height
        
    below_ratio = 1.0 - above_ratio
    
    # Long Rule 1 Check
    long_rule1_ma = bool(is_green and (c_close >= c_ma20) and (above_ratio >= cfg.candle_above_ma_ratio or c_open >= c_ma20))
    # Short Rule 1 Check
    short_rule1_ma = bool(is_red and (c_close <= c_ma20) and (below_ratio >= cfg.candle_above_ma_ratio or c_open <= c_ma20))
    
    pattern_name, pattern_bias = detect_candle_pattern(df, idx=-1)
    long_rule1_pattern = bool(pattern_bias == "BULLISH" or not cfg.require_candle_pattern)
    short_rule1_pattern = bool(pattern_bias == "BEARISH" or not cfg.require_candle_pattern)
    
    rule1_long = long_rule1_ma and (long_rule1_pattern or above_ratio >= 0.70)
    rule1_short = short_rule1_ma and (short_rule1_pattern or below_ratio >= 0.70)
    
    # -------------------------------------------------------------
    # RULE 2: Is RSI(14) crossing RSI(20) from downward to upward?
    # (Or upward to downward for short)
    # -------------------------------------------------------------
    rsi_fast = df['rsi_fast'].values
    rsi_slow = df['rsi_slow'].values
    
    # Check crossover in recent lookback window
    lookback = min(cfg.rsi_crossover_lookback, len(df) - 1)
    rsi_bullish_cross = False
    rsi_bearish_cross = False
    
    for i in range(-lookback, 0):
        # Bullish: previous fast < slow and current fast >= slow
        if rsi_fast[i-1] <= rsi_slow[i-1] and rsi_fast[i] > rsi_slow[i]:
            rsi_bullish_cross = True
            break
        # Or currently fast > slow and crossed within window
        if rsi_fast[i] > rsi_slow[i] and rsi_fast[-lookback] <= rsi_slow[-lookback]:
            rsi_bullish_cross = True
            break
            
    for i in range(-lookback, 0):
        # Bearish: previous fast > slow and current fast <= slow
        if rsi_fast[i-1] >= rsi_slow[i-1] and rsi_fast[i] < rsi_slow[i]:
            rsi_bearish_cross = True
            break
        if rsi_fast[i] < rsi_slow[i] and rsi_fast[-lookback] >= rsi_slow[-lookback]:
            rsi_bearish_cross = True
            break
            
    # Also verify current alignment
    rule2_long = bool(rsi_bullish_cross or (rsi_fast[-1] > rsi_slow[-1] and (rsi_fast[-1] - rsi_slow[-1]) >= 0.5))
    rule2_short = bool(rsi_bearish_cross or (rsi_fast[-1] < rsi_slow[-1] and (rsi_slow[-1] - rsi_fast[-1]) >= 0.5))
    
    # -------------------------------------------------------------
    # RULE 3: Is MACD green?
    # Histogram > 0 and expanding (Hist[t] >= Hist[t-1])
    # -------------------------------------------------------------
    curr_macd_hist = float(curr['macd_hist'])
    prev_macd_hist = float(prev['macd_hist'])
    
    rule3_long = bool(curr_macd_hist > 0 and (curr_macd_hist >= prev_macd_hist or not cfg.require_macd_growing))
    rule3_short = bool(curr_macd_hist < 0 and (curr_macd_hist <= prev_macd_hist or not cfg.require_macd_growing))
    
    # -------------------------------------------------------------
    # RULE 4: Volume of current candle > average volume of the last 5 candles
    # -------------------------------------------------------------
    # Note: We take average of previous 5 completed candles for strict comparison
    prev_5_vols = df['volume'].iloc[-6:-1]
    avg_vol_5 = float(prev_5_vols.mean()) if len(prev_5_vols) > 0 else float(curr['vol_ma5'])
    
    rule4_passed = bool(c_vol >= (avg_vol_5 * cfg.volume_threshold_ratio))
    
    # -------------------------------------------------------------
    # RULE 6: Stop-Loss Calculation & Risk-Reward Target
    # -------------------------------------------------------------
    # Option A: Previous 2 candles low / high
    p2_low = float(min(df['low'].iloc[-2], df['low'].iloc[-3])) if len(df) >= 3 else c_low
    p2_high = float(max(df['high'].iloc[-2], df['high'].iloc[-3])) if len(df) >= 3 else c_high
    
    # Option B: Swing Low / Swing High (last N candles)
    sw_lookback = min(cfg.swing_lookback, len(df))
    swing_low = float(df['low'].iloc[-sw_lookback:].min())
    swing_high = float(df['high'].iloc[-sw_lookback:].max())
    
    # Select SL based on config
    if cfg.sl_mode == "prev_2_candles":
        long_sl = round(min(p2_low, c_low) - (c_close * 0.0005), 2)
        short_sl = round(max(p2_high, c_high) + (c_close * 0.0005), 2)
    elif cfg.sl_mode == "swing_low_high":
        long_sl = round(swing_low - (c_close * 0.0005), 2)
        short_sl = round(swing_high + (c_close * 0.0005), 2)
    else: # auto tighter
        long_sl = round(max(p2_low, swing_low), 2)
        short_sl = round(min(p2_high, swing_high), 2)
        
    # Long Risk and Target
    long_risk = max(c_close - long_sl, c_close * 0.002)
    long_target = round(c_close + (long_risk * cfg.risk_reward_ratio), 2)
    
    # Short Risk and Target
    short_risk = max(short_sl - c_close, c_close * 0.002)
    short_target = round(c_close - (short_risk * cfg.risk_reward_ratio), 2)
    
    # -------------------------------------------------------------
    # Overall Verdict Formation
    # -------------------------------------------------------------
    all_long_rules = [
        pdh_broken if cfg.require_pdh_pdl_break else True,
        rule1_long,
        rule2_long,
        rule3_long,
        rule4_passed
    ]
    
    all_short_rules = [
        pdl_broken if cfg.require_pdh_pdl_break else True,
        rule1_short,
        rule2_short,
        rule3_short,
        rule4_passed
    ]
    
    long_score = sum(1 for r in all_long_rules if r)
    short_score = sum(1 for r in all_short_rules if r)
    
    if all(all_long_rules):
        verdict = "BUY_SIGNAL"
        side = "LONG"
        sl = long_sl
        target = long_target
        risk_points = round(long_risk, 2)
    elif all(all_short_rules):
        verdict = "SELL_SIGNAL"
        side = "SHORT"
        sl = short_sl
        target = short_target
        risk_points = round(short_risk, 2)
    elif pdh_broken and long_score >= 4:
        verdict = "LONG_SETUP_BUILDING"
        side = "LONG"
        sl = long_sl
        target = long_target
        risk_points = round(long_risk, 2)
    elif pdl_broken and short_score >= 4:
        verdict = "SHORT_SETUP_BUILDING"
        side = "SHORT"
        sl = short_sl
        target = short_target
        risk_points = round(short_risk, 2)
    elif not pdh_broken and not pdl_broken and cfg.require_pdh_pdl_break:
        verdict = "WAITING_PDH_PDL_BREAK"
        side = "NEUTRAL"
        sl = 0.0
        target = 0.0
        risk_points = 0.0
    else:
        verdict = "SCANNING"
        side = "NEUTRAL"
        sl = 0.0
        target = 0.0
        risk_points = 0.0

    return {
        "status": "OK",
        "verdict": verdict,
        "side": side,
        "entry_price": round(c_close, 2),
        "stop_loss": sl,
        "target_price": target,
        "risk_reward": cfg.risk_reward_ratio,
        "risk_points": risk_points,
        "scores": {
            "long_score": f"{long_score}/5",
            "short_score": f"{short_score}/5"
        },
        "indicators": {
            "close": round(c_close, 2),
            "ma20": round(c_ma20, 2),
            "rsi14": round(float(curr['rsi_fast']), 2),
            "rsi20": round(float(curr['rsi_slow']), 2),
            "macd_line": round(float(curr['macd_line']), 2),
            "macd_signal": round(float(curr['macd_signal']), 2),
            "macd_hist": round(curr_macd_hist, 2),
            "volume": int(c_vol),
            "volume_avg5": int(avg_vol_5),
            "pdh": round(pdh, 2) if pdh else 0.0,
            "pdl": round(pdl, 2) if pdl else 0.0,
            "candle_above_ma_pct": round(above_ratio * 100, 1),
            "candle_pattern": pattern_name,
            "prev_2_candles_low": round(p2_low, 2),
            "prev_2_candles_high": round(p2_high, 2),
            "swing_low": round(swing_low, 2),
            "swing_high": round(swing_high, 2)
        },
        "rules_breakdown": {
            "pdh_break": {
                "name": "Price Breaks Previous Day High (Long) / Low (Short)",
                "long_passed": pdh_broken,
                "short_passed": pdl_broken,
                "value": f"PDH: {round(pdh, 2)} | PDL: {round(pdl, 2)} | Close: {round(c_close, 2)}"
            },
            "rule1_ma20_candle": {
                "name": "Rule 1: Candle Closes on MA(20) (>60% above/below) + Pattern",
                "long_passed": rule1_long,
                "short_passed": rule1_short,
                "value": f"MA(20): {round(c_ma20, 2)} | {pattern_name} | {round(above_ratio*100, 1)}% above"
            },
            "rule2_rsi_crossover": {
                "name": "Rule 2: RSI(14) Crossover RSI(20)",
                "long_passed": rule2_long,
                "short_passed": rule2_short,
                "value": f"RSI(14): {round(float(curr['rsi_fast']), 1)} vs RSI(20): {round(float(curr['rsi_slow']), 1)}"
            },
            "rule3_macd": {
                "name": "Rule 3: MACD Green / Red (Histogram Confirmation)",
                "long_passed": rule3_long,
                "short_passed": rule3_short,
                "value": f"Hist: {round(curr_macd_hist, 2)} ({'Green' if curr_macd_hist > 0 else 'Red'})"
            },
            "rule4_volume": {
                "name": "Rule 4: Volume > 5-period Volume Average",
                "long_passed": rule4_passed,
                "short_passed": rule4_passed,
                "value": f"Vol: {int(c_vol):,} vs Avg5: {int(avg_vol_5):,}"
            },
            "rule6_stoploss": {
                "name": "Rule 6: Stop-Loss & 1:2 Target Plan",
                "long_passed": True,
                "short_passed": True,
                "value": f"Long SL: {long_sl} (Tgt: {long_target}) | Short SL: {short_sl} (Tgt: {short_target})"
            }
        }
    }
