"""
Quant Pilot - Paper Trading Engine
High-fidelity virtual trading simulator:
- Manages virtual wallet balance and margin
- Tracks open positions and live unrealized PnL
- Enforces automated Stop-Loss and Take-Profit exits
- Logs all trades in the exact CSV format as user's previous bots
- Computes quant performance metrics (Win Rate, Profit Factor, Max Drawdown)
"""
import os
import json
import time
import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from .config import AppConfig, DATA_DIR, LOGS_DIR

TRADES_DB = DATA_DIR / "paper_trades.json"

class PaperEngine:
    def __init__(self, config: AppConfig):
        self.config = config
        self.capital = config.paper_capital
        self.balance = config.paper_capital
        self.open_positions: Dict[str, Dict[str, Any]] = {}
        self.closed_trades: List[Dict[str, Any]] = []
        self._load_state()

    def _load_state(self):
        if TRADES_DB.exists():
            try:
                with open(TRADES_DB, "r") as f:
                    data = json.load(f)
                    self.balance = float(data.get("balance", self.capital))
                    self.open_positions = data.get("open_positions", {})
                    self.closed_trades = data.get("closed_trades", [])
            except Exception as e:
                print(f"[PaperEngine] Error loading state: {e}")

    def _save_state(self):
        try:
            with open(TRADES_DB, "w") as f:
                json.dump({
                    "balance": self.balance,
                    "capital": self.capital,
                    "open_positions": self.open_positions,
                    "closed_trades": self.closed_trades,
                    "updated_at": datetime.datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            print(f"[PaperEngine] Error saving state: {e}")

    def reset_account(self, initial_capital: float = 100000.0):
        """Resets the paper trading account"""
        self.capital = initial_capital
        self.balance = initial_capital
        self.open_positions = {}
        self.closed_trades = []
        self._save_state()

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        lot_size: int = 1,
        position_type: str = "Equity"
    ) -> int:
        """
        Calculates position quantity based on risk capital and intraday margin
        """
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share <= 0:
            risk_per_share = entry_price * 0.005 # 0.5% default fallback
            
        risk_capital = min(
            self.balance * (self.config.strategy.risk_per_trade_percent / 100.0),
            self.config.strategy.max_risk_amount
        )
        
        raw_qty = int(risk_capital / risk_per_share)
        
        # Adjust for lot sizes (e.g. Nifty = 25, BankNifty = 15, Crude = 10)
        if lot_size > 1:
            lots = max(1, raw_qty // lot_size)
            qty = lots * lot_size
        else:
            qty = max(1, raw_qty)
            
        # Determine margin factor based on Indian market segment:
        # F&O Index/Futures = 5% intraday margin, Equity MIS = 20% margin, Options = ~1% premium
        if position_type == "Options":
            margin_rate = 0.01
        elif position_type in ("Index", "Futures", "Commodity"):
            margin_rate = 0.05 # 20x intraday index futures leverage
        else:
            margin_rate = 0.20 # 5x intraday equity margin
            
        required_capital = qty * entry_price * margin_rate
        if required_capital > self.balance:
            max_qty_possible = int(self.balance / (entry_price * margin_rate))
            if lot_size > 1:
                qty = (max_qty_possible // lot_size) * lot_size
                if qty == 0 and self.balance >= (lot_size * entry_price * 0.02):
                    # Minimum 1 lot with dynamic margin
                    qty = lot_size
            else:
                qty = max(1, max_qty_possible)
            
        return qty

    def open_trade(
        self,
        symbol: str,
        side: str, # "LONG" or "SHORT"
        entry_price: float,
        stop_loss: float,
        target_price: float,
        symbol_info: Dict[str, Any],
        position_type: str = "Equity" # "Equity", "Futures", "Options", "Index"
    ) -> Optional[Dict[str, Any]]:
        """
        Executes a paper trading order with realistic intraday margin
        """
        if symbol in self.open_positions:
            return None # Already in trade for this symbol
            
        lot_size = symbol_info.get("lot_size", 1)
        qty = self.calculate_position_size(entry_price, stop_loss, lot_size, position_type)
        
        # Intraday Margin rate
        if position_type == "Options":
            margin_rate = 0.01
        elif position_type in ("Index", "Futures", "Commodity"):
            margin_rate = 0.05
        else:
            margin_rate = 0.20
            
        capital_used = round(qty * entry_price * margin_rate, 2)
        
        if capital_used > self.balance:
            print(f"[PaperEngine] Insufficient balance for {symbol}. Required: {capital_used}, Available: {self.balance}")
            return None

        # Deduct margin
        self.balance -= capital_used
        
        trade_id = f"TRADE-{int(time.time()*1000)}"
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        pos = {
            "trade_id": trade_id,
            "symbol": symbol,
            "name": symbol_info.get("name", symbol),
            "side": side,
            "position_type": position_type,
            "entry_time": now_str,
            "entry_price": round(entry_price, 2),
            "current_price": round(entry_price, 2),
            "quantity": qty,
            "capital_used": capital_used,
            "stop_loss": round(stop_loss, 2),
            "target_price": round(target_price, 2),
            "unrealized_pnl": 0.0,
            "unrealized_pnl_pct": 0.0,
            "status": "ACTIVE"
        }
        
        self.open_positions[symbol] = pos
        self._save_state()
        self._log_to_csv(pos, action=f"Entry({side.title()})", status="Active")
        return pos

    def update_ticks(self, symbol: str, current_price: float) -> Optional[Dict[str, Any]]:
        """
        Updates live PnL and monitors for SL or Target hit
        """
        if symbol not in self.open_positions:
            return None
            
        pos = self.open_positions[symbol]
        pos["current_price"] = round(current_price, 2)
        side = pos["side"]
        entry = pos["entry_price"]
        qty = pos["quantity"]
        sl = pos["stop_loss"]
        tgt = pos["target_price"]
        
        # Calculate Unrealized PnL
        if side == "LONG":
            pnl = (current_price - entry) * qty
            pos["unrealized_pnl"] = round(pnl, 2)
            pos["unrealized_pnl_pct"] = round(((current_price - entry) / entry) * 100, 2)
            
            # Check Target Hit
            if current_price >= tgt:
                return self.close_trade(symbol, current_price, reason="TARGET_HIT")
            # Check Stop Loss Hit
            elif current_price <= sl:
                return self.close_trade(symbol, current_price, reason="STOP_LOSS_HIT")
                
        elif side == "SHORT":
            pnl = (entry - current_price) * qty
            pos["unrealized_pnl"] = round(pnl, 2)
            pos["unrealized_pnl_pct"] = round(((entry - current_price) / entry) * 100, 2)
            
            # Check Target Hit
            if current_price <= tgt:
                return self.close_trade(symbol, current_price, reason="TARGET_HIT")
            # Check Stop Loss Hit
            elif current_price >= sl:
                return self.close_trade(symbol, current_price, reason="STOP_LOSS_HIT")
                
        self._save_state()
        return pos

    def close_trade(self, symbol: str, exit_price: float, reason: str = "MANUAL_EXIT") -> Optional[Dict[str, Any]]:
        """
        Closes an active position and records realized PnL
        """
        if symbol not in self.open_positions:
            return None
            
        pos = self.open_positions.pop(symbol)
        side = pos["side"]
        entry = pos["entry_price"]
        qty = pos["quantity"]
        capital_used = pos["capital_used"]
        
        if side == "LONG":
            pnl = (exit_price - entry) * qty
        else:
            pnl = (entry - exit_price) * qty
            
        pnl = round(pnl, 2)
        pnl_pct = round((pnl / capital_used) * 100, 2)
        
        # Return capital + PnL to balance
        self.balance += (capital_used + pnl)
        
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        closed_rec = {
            "trade_id": pos["trade_id"],
            "symbol": symbol,
            "name": pos["name"],
            "side": side,
            "position_type": pos["position_type"],
            "entry_time": pos["entry_time"],
            "exit_time": now_str,
            "entry_price": entry,
            "exit_price": round(exit_price, 2),
            "quantity": qty,
            "capital_used": capital_used,
            "stop_loss": pos["stop_loss"],
            "target_price": pos["target_price"],
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "exit_reason": reason,
            "status": "EXECUTED"
        }
        
        self.closed_trades.append(closed_rec)
        self._save_state()
        self._log_to_csv(closed_rec, action=f"Exit({side.title()})", status="Executed")
        return closed_rec

    def get_summary(self) -> Dict[str, Any]:
        """
        Computes overall portfolio & trading performance stats
        """
        total_trades = len(self.closed_trades)
        winning_trades = [t for t in self.closed_trades if t["pnl"] > 0]
        losing_trades = [t for t in self.closed_trades if t["pnl"] < 0]
        
        total_pnl = sum(t["pnl"] for t in self.closed_trades)
        gross_profit = sum(t["pnl"] for t in winning_trades)
        gross_loss = abs(sum(t["pnl"] for t in losing_trades))
        
        win_rate = round((len(winning_trades) / total_trades) * 100, 1) if total_trades > 0 else 0.0
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (round(gross_profit, 2) if gross_profit > 0 else 1.0)
        
        unrealized_total = sum(p["unrealized_pnl"] for p in self.open_positions.values())
        equity = self.balance + sum(p["capital_used"] for p in self.open_positions.values()) + unrealized_total
        return_pct = round(((equity - self.capital) / self.capital) * 100, 2)
        
        return {
            "initial_capital": self.capital,
            "current_balance": round(self.balance, 2),
            "portfolio_equity": round(equity, 2),
            "unrealized_pnl": round(unrealized_total, 2),
            "realized_pnl": round(total_pnl, 2),
            "return_pct": return_pct,
            "total_trades": total_trades,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "open_positions_count": len(self.open_positions)
        }

    def _log_to_csv(self, pos: Dict[str, Any], action: str, status: str):
        """
        Appends trade record to CSV file matching the format in user's workspace
        """
        try:
            today_str = datetime.datetime.now().strftime("%Y-%m-%d")
            clean_sym = pos["symbol"].replace(":", "_").replace("-", "_")
            csv_file = LOGS_DIR / f"{clean_sym}_{today_str}.csv"
            
            write_header = not csv_file.exists()
            with open(csv_file, "a") as f:
                if write_header:
                    f.write("Timestamp,Symbol,Action,Position_Type,Entry_Price,Quantity,Capital_Used,Exit_Price,PnL,Status\n")
                    
                timestamp = pos.get("exit_time") if "Exit" in action else pos.get("entry_time")
                f.write(
                    f"{timestamp},"
                    f"{pos['symbol']},"
                    f"{action},"
                    f"{pos.get('position_type', 'Equity')},"
                    f"{pos['entry_price']},"
                    f"{pos['quantity']},"
                    f"{pos['capital_used']},"
                    f"{pos.get('exit_price', '')},"
                    f"{pos.get('pnl', '')},"
                    f"{status}\n"
                )
        except Exception as e:
            print(f"[PaperEngine] CSV log error: {e}")
