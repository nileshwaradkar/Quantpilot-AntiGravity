"""
Quant Pilot - Application Entry Point
Starts Uvicorn ASGI server hosting the Quant Pilot Web Application
"""
import os
import sys
import uvicorn
from app.web_server import app


def main():
    port = int(os.environ.get("PORT", 7860))
    host = os.environ.get("HOST", "0.0.0.0")
    print("=" * 60)
    print("🚀 QUANT PILOT - Intraday Trading Assistant")
    print("=" * 60)
    print(f"📡 Local Windows Browser: http://localhost:{port}")
    print(f"📱 iPhone Safari: Access via deployed Cloud URL or LAN IP")
    print("=" * 60)
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    main()
