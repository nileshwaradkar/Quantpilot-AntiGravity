"""
Quant Pilot - FastAPI Web Server & Real-time Engine
High-performance async server powering:
- REST API for charts, scanner, strategy metrics, and trade management
- WebSocket streaming for tick-by-tick updates to Windows browser and iPhone Safari
- Background quantitative scanner continuously evaluating all 6 intraday rules
"""
import os
import json
import asyncio
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import (
    BASE_DIR, DEFAULT_WATCHLIST, AppConfig,
    load_app_config, save_app_config
)
from .strategy_engine import evaluate_intraday_strategy
from .market_data import MarketDataProvider
from .paper_engine import PaperEngine
from .broker_fyers import FyersBroker
from .notifier import NotificationDispatcher

app = FastAPI(title="Quant Pilot - Intraday Trading Assistant")

# Mount static and templates
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# App State
app_config = load_app_config()
market_data = MarketDataProvider(app_config)
paper_engine = PaperEngine(app_config)
fyers_broker = FyersBroker(app_config)
notifier = NotificationDispatcher(app_config)

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()

# Global Scanner Cache
scanner_results: Dict[str, Dict[str, Any]] = {}
active_symbol = "NSE:NIFTY50-INDEX"

@app.on_event("startup")
async def startup_event():
    # Start background quantitative scanner loop (unless running in test mode)
    if not os.environ.get("TESTING"):
        asyncio.create_task(background_scanner_loop())

async def background_scanner_loop():
    """
    Background continuous scanner:
    Evaluates intraday rules for each symbol in watchlist every few seconds,
    updates paper positions, checks SL/Target, and broadcasts to clients.
    """
    global scanner_results
    while True:
        try:
            for item in DEFAULT_WATCHLIST:
                sym = item["symbol"]
                # 1. Fetch candles
                df, pdh, pdl = market_data.fetch_candles(sym, resolution="5m", count=100)
                if df is not None and len(df) >= 25:
                    # 2. Evaluate 6 intraday rules
                    result = evaluate_intraday_strategy(df, pdh, pdl, app_config.strategy)
                    result["symbol"] = sym
                    result["name"] = item["name"]
                    result["exchange"] = item.get("exchange", "NSE")
                    scanner_results[sym] = result
                    
                    # 3. Update Paper Engine ticks & check SL / Target hits
                    curr_price = float(df['close'].iloc[-1])
                    updated_pos = paper_engine.update_ticks(sym, curr_price)
                    
                    # 4. Check for auto-paper trade trigger on strong signal
                    if (
                        result.get("verdict") in ("BUY_SIGNAL", "SELL_SIGNAL")
                        and sym not in paper_engine.open_positions
                        and app_config.trading_mode == "PAPER"
                    ):
                        side = "LONG" if result.get("verdict") == "BUY_SIGNAL" else "SHORT"
                        new_pos = paper_engine.open_trade(
                            symbol=sym,
                            side=side,
                            entry_price=result["entry_price"],
                            stop_loss=result["stop_loss"],
                            target_price=result["target_price"],
                            symbol_info=item,
                            position_type="Index" if "INDEX" in sym else ("Commodity" if "CRUDE" in sym else "Equity")
                        )
                        if new_pos:
                            notifier.send_signal_alert(result)
                            await ws_manager.broadcast({
                                "type": "TRADE_ALERT",
                                "data": {
                                    "symbol": sym,
                                    "action": f"Auto Paper Order: {side}",
                                    "verdict": result["verdict"],
                                    "entry": result["entry_price"],
                                    "sl": result["stop_loss"],
                                    "target": result["target_price"]
                                }
                            })
                            
            # Broadcast scanner matrix update to all connected Windows and Safari devices
            summary = paper_engine.get_summary()
            market_status = market_data.get_market_status()
            
            await ws_manager.broadcast({
                "type": "SCANNER_UPDATE",
                "data": {
                    "scanner": list(scanner_results.values()),
                    "portfolio": summary,
                    "market_status": market_status,
                    "trading_mode": app_config.trading_mode
                }
            })
            
        except Exception as e:
            print(f"[ScannerLoop] Error: {e}")
            
        await asyncio.sleep(4.0)

# -------------------------------------------------------------
# REST API Endpoints
# -------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "watchlist": DEFAULT_WATCHLIST,
        "default_symbol": active_symbol,
        "config": app_config
    })

@app.get("/api/watchlist")
def get_watchlist():
    return {
        "watchlist": DEFAULT_WATCHLIST,
        "scanner": list(scanner_results.values())
    }

@app.get("/api/candles/{symbol}")
def get_candles(symbol: str):
    df, pdh, pdl = market_data.fetch_candles(symbol, resolution="5m", count=120)
    if df is None or len(df) == 0:
        raise HTTPException(status_code=404, detail="Candles not found")
        
    df_with_ind = evaluate_intraday_strategy(df, pdh, pdl, app_config.strategy)
    
    # Format candles for TradingView Lightweight Charts
    # Lightweight Charts expects: { time: epoch_in_seconds, open, high, low, close }
    candles_data = []
    ma20_data = []
    volume_data = []
    rsi_data = []
    macd_data = []
    
    # Compute indicators for full chart
    from .strategy_engine import calculate_indicators
    df_calc = calculate_indicators(df, app_config.strategy)
    
    for idx, row in df_calc.iterrows():
        t = int(row['timestamp'])
        c_open = round(float(row['open']), 2)
        c_high = round(float(row['high']), 2)
        c_low = round(float(row['low']), 2)
        c_close = round(float(row['close']), 2)
        c_vol = round(float(row['volume']), 0)
        
        candles_data.append({"time": t, "open": c_open, "high": c_high, "low": c_low, "close": c_close})
        
        if not pd.isna(row.get('ma20')):
            ma20_data.append({"time": t, "value": round(float(row['ma20']), 2)})
            
        vol_color = "rgba(38, 166, 154, 0.5)" if c_close >= c_open else "rgba(239, 83, 80, 0.5)"
        volume_data.append({"time": t, "value": c_vol, "color": vol_color})
        
        if not pd.isna(row.get('rsi_fast')):
            rsi_data.append({
                "time": t,
                "rsi14": round(float(row['rsi_fast']), 2),
                "rsi20": round(float(row['rsi_slow']), 2)
            })
            
        if not pd.isna(row.get('macd_hist')):
            hist = round(float(row['macd_hist']), 2)
            hist_color = "#26a69a" if hist >= 0 else "#ef5350"
            macd_data.append({
                "time": t,
                "macd": round(float(row['macd_line']), 2),
                "signal": round(float(row['macd_signal']), 2),
                "hist": hist,
                "hist_color": hist_color
            })
            
    eval_result = scanner_results.get(symbol, df_with_ind)
    
    return {
        "symbol": symbol,
        "pdh": pdh,
        "pdl": pdl,
        "candles": candles_data,
        "ma20": ma20_data,
        "volume": volume_data,
        "rsi": rsi_data,
        "macd": macd_data,
        "evaluation": eval_result
    }

@app.get("/api/evaluate/{symbol}")
def evaluate_symbol(symbol: str):
    if symbol in scanner_results:
        return scanner_results[symbol]
    df, pdh, pdl = market_data.fetch_candles(symbol, resolution="5m", count=100)
    result = evaluate_intraday_strategy(df, pdh, pdl, app_config.strategy)
    return result

@app.get("/api/paper/portfolio")
def get_portfolio():
    summary = paper_engine.get_summary()
    return {
        "summary": summary,
        "open_positions": list(paper_engine.open_positions.values()),
        "closed_trades": list(reversed(paper_engine.closed_trades))
    }

@app.post("/api/paper/order")
async def execute_paper_order(request: Request):
    data = await request.json()
    sym = data.get("symbol")
    side = data.get("side", "LONG").upper()
    entry_price = float(data.get("entry_price", 0.0))
    stop_loss = float(data.get("stop_loss", 0.0))
    target_price = float(data.get("target_price", 0.0))
    
    info = market_data.get_symbol_info(sym)
    if entry_price <= 0:
        df, _, _ = market_data.fetch_candles(sym, resolution="5m", count=10)
        entry_price = float(df['close'].iloc[-1])
        if side == "LONG":
            stop_loss = entry_price * 0.995
            target_price = entry_price * 1.010
        else:
            stop_loss = entry_price * 1.005
            target_price = entry_price * 0.990
            
    pos = paper_engine.open_trade(
        symbol=sym,
        side=side,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_price=target_price,
        symbol_info=info,
        position_type="Equity" if "EQ" in sym else ("Commodity" if "CRUDE" in sym else "Index")
    )
    if not pos:
        raise HTTPException(status_code=400, detail="Cannot open trade. Insufficient funds or already in trade.")
    return {"status": "SUCCESS", "position": pos}

@app.post("/api/paper/close")
async def close_paper_order(request: Request):
    data = await request.json()
    sym = data.get("symbol")
    exit_price = data.get("exit_price")
    
    if sym not in paper_engine.open_positions:
        raise HTTPException(status_code=404, detail="Position not found")
        
    if not exit_price:
        df, _, _ = market_data.fetch_candles(sym, count=10)
        exit_price = float(df['close'].iloc[-1])
    else:
        exit_price = float(exit_price)
        
    trade = paper_engine.close_trade(sym, exit_price, reason="MANUAL_SQUARE_OFF")
    return {"status": "SUCCESS", "closed_trade": trade}

@app.post("/api/paper/reset")
async def reset_paper_capital(request: Request):
    data = await request.json()
    capital = float(data.get("capital", 100000.0))
    paper_engine.reset_account(capital)
    return {"status": "SUCCESS", "message": f"Account reset to ₹{capital:,.2f}"}

@app.get("/api/broker/status")
def get_broker_status():
    status = fyers_broker.get_profile()
    return status

@app.get("/api/broker/login-url")
def get_broker_login_url():
    url = fyers_broker.get_login_url()
    return {"login_url": url}

@app.post("/api/broker/authcode")
async def submit_auth_code(request: Request):
    data = await request.json()
    code = data.get("auth_code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="auth_code required")
    res = fyers_broker.generate_token_from_authcode(code)
    return res

@app.get("/api/settings")
def get_settings():
    return app_config.model_dump()

@app.post("/api/settings")
async def update_settings(request: Request):
    global app_config
    data = await request.json()
    try:
        updated = AppConfig.model_validate(data)
        save_app_config(updated)
        app_config = updated
        market_data.config = updated
        paper_engine.config = updated
        fyers_broker.config = updated
        notifier.config = updated
        return {"status": "SUCCESS", "message": "Settings updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/market-status")
def get_market_status():
    return market_data.get_market_status()

# -------------------------------------------------------------
# WebSocket Handler
# -------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        # Send initial snapshot immediately
        summary = paper_engine.get_summary()
        m_status = market_data.get_market_status()
        await websocket.send_json({
            "type": "INITIAL_STATE",
            "data": {
                "scanner": list(scanner_results.values()),
                "portfolio": summary,
                "open_positions": list(paper_engine.open_positions.values()),
                "market_status": m_status,
                "trading_mode": app_config.trading_mode
            }
        })
        while True:
            # Keep connection open & handle incoming client messages
            msg = await websocket.receive_text()
            data = json.loads(msg)
            if data.get("action") == "SELECT_SYMBOL":
                global active_symbol
                active_symbol = data.get("symbol", active_symbol)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
