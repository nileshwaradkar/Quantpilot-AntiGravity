"""
Candle module for Sync Indicator library.

Provides the OHLC (Open, High, Low, Close, Volume) candle class for financial data.

Author: anodicpassion
License: MIT
"""

import numpy as np


class OHLC:
    """
    Represents a single OHLCV (Open, High, Low, Close, Volume) candle.
    Each candle is expected to be a numpy array of shape (6,):
    [timestamp, open, high, low, close, volume]
    """

    def __init__(self, candle: np.ndarray) -> None:
        """
        Initialize an OHLC object from a numpy array.

        Args:
            candle (np.ndarray): Array of shape (6,) representing [timestamp, open, high, low, close, volume].

        Raises:
            ValueError: If the input is not a numpy array of shape (6,).
            TypeError: If any value is not of the expected type.
        """
        if candle is None or not isinstance(candle, np.ndarray):
            raise ValueError("candle must be a non-empty numpy.ndarray")
        if candle.shape != (6,):
            raise ValueError("candle must have shape (6,)")
        if not (isinstance(candle[0], (float, int, np.integer)) and candle[0] > 0):
            raise TypeError("timestamp must be a positive float or int (POSIX time)")
        self._timestamp = int(candle[0])
        self._open = float(candle[1])
        self._high = float(candle[2])
        self._low = float(candle[3])
        self._close = float(candle[4])
        self._volume = float(candle[5])

    def timestamp(self) -> int:
        """
        Returns the timestamp of the candle (POSIX time).
        Returns:
            int: The timestamp.
        """
        return self._timestamp

    def open(self) -> float:
        """
        Returns the open price of the candle.
        Returns:
            float: The open price.
        """
        return round(self._open, 2)

    def high(self) -> float:
        """
        Returns the high price of the candle.
        Returns:
            float: The high price.
        """
        return round(self._high, 2)

    def low(self) -> float:
        """
        Returns the low price of the candle.
        Returns:
            float: The low price.
        """
        return round(self._low, 2)

    def close(self) -> float:
        """
        Returns the close price of the candle.
        Returns:
            float: The close price.
        """
        return round(self._close, 2)

    def volume(self) -> float:
        """
        Returns the volume of the candle.
        Returns:
            float: The volume.
        """
        return round(self._volume, 2)

    def to_numpy(self) -> np.ndarray:
        """
        Returns the candle as a numpy array: [timestamp, open, high, low, close, volume].
        Returns:
            np.ndarray: The candle data.
        """
        return np.array([
            self._timestamp,
            round(self._open, 2),
            round(self._high, 2),
            round(self._low, 2),
            round(self._close, 2),
            round(self._volume, 2)
        ], dtype=np.float64)

    def __call__(self) -> np.ndarray:
        """
        Callable interface to return the candle as a numpy array.
        Returns:
            np.ndarray: The candle data.
        """
        return self.to_numpy()
