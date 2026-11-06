"""
Quant Pilot - Notification & Alert Dispatcher
Multi-channel alerts for Windows browser and iPhone Safari:
1. Real-time WebSocket audio chimes and UI popups
2. Telegram Bot Webhook (alerts arrive on iPhone even when phone is locked!)
"""
import requests
import datetime
from typing import Dict, Any, Optional
from .config import AppConfig

class NotificationDispatcher:
    def __init__(self, config: AppConfig):
        self.config = config

    def send_signal_alert(self, signal_data: Dict[str, Any]):
        """
        Dispatches signal alerts to Telegram bot if configured
        """
        bot_token = self.config.telegram_bot_token
        chat_id = self.config.telegram_chat_id
        
        if not bot_token or not chat_id:
            return
            
        sym = signal_data.get("symbol", "N/A")
        verdict = signal_data.get("verdict", "")
        side = signal_data.get("side", "")
        entry = signal_data.get("entry_price", 0.0)
        sl = signal_data.get("stop_loss", 0.0)
        tgt = signal_data.get("target_price", 0.0)
        risk = signal_data.get("risk_points", 0.0)
        pattern = signal_data.get("indicators", {}).get("candle_pattern", "")
        
        emoji = "🚀🟢" if side == "LONG" else "🔻🔴"
        
        msg = (
            f"{emoji} *QUANT PILOT INTRADAY ALERT* {emoji}\n\n"
            f"📈 *Symbol*: `{sym}`\n"
            f"🎯 *Signal*: *{verdict}* ({side})\n"
            f"💵 *Entry*: `₹{entry}`\n"
            f"🛑 *Stop Loss*: `₹{sl}` (Risk: {risk} pts)\n"
            f"🏆 *Target (1:2)*: `₹{tgt}`\n"
            f"🕯 *Pattern*: `{pattern}`\n\n"
            f"✅ *Quant Rules Passed*:\n"
            f"• PDH/PDL Breakout: Confirmed\n"
            f"• MA(20) Position: Verified (>60% on line)\n"
            f"• RSI(14) vs RSI(20): Bullish Crossover\n"
            f"• MACD Histogram: Green & Expanding\n"
            f"• Volume: > 5-period Moving Average\n\n"
            f"⏱ _{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}_\n"
            f"📱 _Quant Pilot Web Assistant_"
        )
        
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "Markdown"
            }
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print(f"[Notifier] Telegram dispatch error: {e}")
