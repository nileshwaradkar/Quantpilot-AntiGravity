"""
Quant Pilot - Fyers Broker Integration
Direct connectivity to Fyers API v3 for:
- One-click OAuth login and token exchange
- Real-time profile & funds query
- Option chain analysis (ATM Call & Put strike selection)
- Bracket Order (BO) and Market order execution with SL & Target
"""
import json
import time
import requests
from typing import Dict, List, Optional, Any
from .config import AppConfig, save_app_config

class FyersBroker:
    def __init__(self, config: AppConfig):
        self.config = config
        self.base_url = "https://api-t1.fyers.in/api/v3"
        self.data_url = "https://api-t1.fyers.in/data"

    def is_connected(self) -> bool:
        return bool(self.config.fyers_access_token and self.config.fyers_client_id)

    def _headers(self) -> Dict[str, str]:
        auth = f"{self.config.fyers_client_id}:{self.config.fyers_access_token}"
        return {
            "Authorization": auth,
            "Content-Type": "application/json"
        }

    def get_login_url(self) -> str:
        """
        Generates Fyers OAuth login authorization URL
        """
        client_id = self.config.fyers_client_id
        redirect_uri = self.config.fyers_redirect_uri
        state = "quant_pilot_state"
        return (
            f"https://api-t1.fyers.in/api/v3/generate-authcode"
            f"?client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&response_type=code"
            f"&state={state}"
        )

    def generate_token_from_authcode(self, auth_code: str) -> Dict[str, Any]:
        """
        Exchanges auth code for access token
        """
        import hashlib
        app_id_hash = hashlib.sha256(f"{self.config.fyers_client_id}:{self.config.fyers_secret_key}".encode()).hexdigest()
        
        payload = {
            "grant_type": "authorization_code",
            "appIdHash": app_id_hash,
            "code": auth_code
        }
        
        try:
            res = requests.post(f"{self.base_url}/validate-authcode", json=payload, timeout=8)
            data = res.json()
            if data.get("s") == "ok" and "access_token" in data:
                token = data["access_token"]
                self.config.fyers_access_token = token
                save_app_config(self.config)
                return {"status": "SUCCESS", "message": "Successfully authenticated with Fyers", "token": token}
            else:
                return {"status": "ERROR", "message": data.get("message", "Token generation failed")}
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}

    def get_profile(self) -> Dict[str, Any]:
        """
        Fetches user profile and fund limits
        """
        if not self.is_connected():
            return {"connected": False, "message": "Fyers credentials not configured"}
            
        try:
            # 1. Profile
            p_res = requests.get(f"{self.base_url}/profile", headers=self._headers(), timeout=5)
            # 2. Funds
            f_res = requests.get(f"{self.base_url}/funds", headers=self._headers(), timeout=5)
            
            p_data = p_res.json() if p_res.status_code == 200 else {}
            f_data = f_res.json() if f_res.status_code == 200 else {}
            
            if p_data.get("s") == "ok":
                profile = p_data.get("data", {})
                fund_limit = 0.0
                if f_data.get("s") == "ok":
                    for item in f_data.get("fund_limit", []):
                        if item.get("title") == "Total Balance":
                            fund_limit = float(item.get("equityAmount", 0.0))
                            break
                            
                return {
                    "connected": True,
                    "name": profile.get("name", "Trader"),
                    "fy_id": profile.get("fy_id", ""),
                    "email": profile.get("email_id", ""),
                    "fund_balance": fund_limit,
                    "market_status": "ONLINE"
                }
            else:
                return {
                    "connected": False,
                    "message": p_data.get("message", "Fyers session expired. Please re-login.")
                }
        except Exception as e:
            return {"connected": False, "message": str(e)}

    def get_atm_option_symbol(self, underlying: str, current_price: float, option_type: str = "CE") -> Optional[str]:
        """
        Retrieves ATM Option symbol (CE or PE) from Fyers Option Chain API
        """
        if not self.is_connected():
            return None
            
        try:
            url = f"{self.data_url}/options-chain-v3?symbol={underlying}&strikecount=5"
            res = requests.get(url, headers=self._headers(), timeout=6)
            if res.status_code == 200:
                data = res.json()
                if data.get("s") == "ok":
                    chain = data.get("data", {}).get("optionsChain", [])
                    # Find closest strike
                    best_opt = None
                    min_diff = float("inf")
                    for opt in chain:
                        if opt.get("option_type") == option_type:
                            strike = opt.get("strike_price", 0)
                            diff = abs(strike - current_price)
                            if diff < min_diff:
                                min_diff = diff
                                best_opt = opt.get("symbol")
                    return best_opt
        except Exception as e:
            print(f"[FyersBroker] Option chain error: {e}")
            
        return None

    def place_bracket_order(
        self,
        symbol: str,
        qty: int,
        side: str, # "BUY" (1) or "SELL" (-1)
        limit_price: float,
        stop_loss_points: float,
        target_points: float
    ) -> Dict[str, Any]:
        """
        Places a Bracket Order (BO) with automated Stop Loss and Take Profit
        """
        if not self.is_connected():
            return {"status": "ERROR", "message": "Fyers broker not connected"}
            
        order_side = 1 if side == "BUY" else -1
        
        payload = {
            "symbol": symbol,
            "qty": qty,
            "type": 2, # Market or Limit
            "side": order_side,
            "productType": "BO",
            "limitPrice": 0.0,
            "stopPrice": 0.0,
            "validity": "DAY",
            "disclosedQty": 0,
            "offlineOrder": False,
            "stopLoss": round(stop_loss_points, 1),
            "takeProfit": round(target_points, 1)
        }
        
        try:
            res = requests.post(f"{self.base_url}/orders/sync", headers=self._headers(), json=payload, timeout=7)
            data = res.json()
            if data.get("s") == "ok":
                return {
                    "status": "SUCCESS",
                    "order_id": data.get("id"),
                    "message": "Bracket order placed successfully on Fyers"
                }
            else:
                return {
                    "status": "ERROR",
                    "code": data.get("code"),
                    "message": data.get("message", "Fyers order placement failed")
                }
        except Exception as e:
            return {"status": "ERROR", "message": str(e)}
