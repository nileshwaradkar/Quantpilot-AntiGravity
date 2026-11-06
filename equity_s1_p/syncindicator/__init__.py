"""
Sync Indicator - A Python library for synchronized technical indicators.

This library provides a comprehensive set of technical indicators for financial
analysis with synchronized data handling capabilities.

Author: anodicpassion
License: MIT
"""

import datetime
import time
from typing import Union

from .syncind import SyncInd
from .classic import (
    SMA, SmoothMA, Alligator, RSI, EMA, MACD, ATR, RMA, WMA,
    VolumeROC, KAMA, BollingerBands
)
from .candle import OHLC

__version__ = "1.0.0"
__author__ = "anodicpassion"
__email__ = "er.pratiksp@gmail.com"
__all__ = [
    "SyncInd", "SMA", "SmoothMA", "Alligator", "RSI", "EMA", "MACD", "ATR", "RMA", "WMA",
    "VolumeROC", "KAMA", "BollingerBands", "OHLC", "Balance", "Broker", "time_to_epoch", "epoch_to_time"
]


def time_to_epoch(date_string: str) -> int:
    """
    Convert a datetime string to epoch timestamp.

    Args:
        date_string (str): Date string in format 'YYYY-MM-DD HH:MM:SS'.

    Returns:
        int: Epoch timestamp.

    Raises:
        ValueError: If date_string format is invalid.
    """
    try:
        date_obj = datetime.datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")
        epoch_time = int(time.mktime(date_obj.timetuple()))
        return epoch_time
    except ValueError as e:
        raise ValueError(f"Invalid date format. Expected 'YYYY-MM-DD HH:MM:SS', got: {date_string}") from e


def epoch_to_time(epoch: Union[int, float]) -> str:
    """
    Convert epoch timestamp to datetime string.

    Args:
        epoch (Union[int, float]): Epoch timestamp.

    Returns:
        str: Date string in format 'YYYY-MM-DD HH:MM:SS'.
    """
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(epoch)))
