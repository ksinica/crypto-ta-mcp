"""Binance API client for fetching market data."""

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

# Base URLs
SPOT_BASE_URL = "https://api.binance.com"
FUTURES_BASE_URL = "https://fapi.binance.com"

# Retry configuration (Binance rate limits and transient 5xx are common)
RETRYABLE_STATUS_CODES: set[int] = {429, 500, 502, 503, 504}
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_SECONDS = 0.5
DEFAULT_BACKOFF_MAX_SECONDS = 8.0

# Timeframe configurations
TIMEFRAME_CONFIG = {
    "monthly": {"interval": "1M", "limit": 60},
    "weekly": {"interval": "1w", "limit": 208},
    "daily": {"interval": "1d", "limit": 250},
}


@dataclass
class KlineData:
    """Raw kline/candle data from Binance."""

    timestamp: int  # Open time in ms
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class FundingRateData:
    """Funding rate data."""

    rate: float
    timestamp: int


@dataclass
class OpenInterestData:
    """Open interest data."""

    value: float  # OI in base currency
    timestamp: int


class BinanceAPIError(Exception):
    """Custom exception for Binance API errors."""

    pass


class BinanceClient:
    """Async client for Binance API."""

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_seconds: float = DEFAULT_BACKOFF_BASE_SECONDS,
        backoff_max_seconds: float = DEFAULT_BACKOFF_MAX_SECONDS,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.backoff_max_seconds = backoff_max_seconds
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BinanceClient":
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Client not initialized. Use async context manager.")
        return self._client

    async def _request(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """Make an HTTP GET request with retry/backoff for transient failures."""
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.get(url, params=params)
                response.raise_for_status()

                try:
                    return response.json()
                except ValueError as e:
                    # Binance should return JSON; if it doesn't, surface a clear error
                    text = response.text
                    snippet = text[:500] + ("..." if len(text) > 500 else "")
                    raise BinanceAPIError(f"Non-JSON response from Binance: {snippet}") from e

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                last_error = e

                if status in RETRYABLE_STATUS_CODES and attempt < self.max_retries:
                    retry_after = e.response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except ValueError:
                            delay = self.backoff_base_seconds * (2**attempt)
                    else:
                        delay = self.backoff_base_seconds * (2**attempt)

                    delay = min(delay, self.backoff_max_seconds)
                    await asyncio.sleep(delay)
                    continue

                raise BinanceAPIError(f"HTTP error {status}: {e.response.text}") from e

            except (httpx.TimeoutException, httpx.RequestError) as e:
                last_error = e

                if attempt < self.max_retries:
                    delay = min(self.backoff_base_seconds * (2**attempt), self.backoff_max_seconds)
                    await asyncio.sleep(delay)
                    continue

                raise BinanceAPIError(f"Request failed: {e}") from e

        # Should be unreachable due to raises above, but keep a safe fallback.
        raise BinanceAPIError(f"Request failed after retries: {last_error}") from last_error

    def _parse_kline(self, kline: list[Any]) -> KlineData:
        """Parse a single kline from Binance API response."""
        return KlineData(
            timestamp=int(kline[0]),
            open=float(kline[1]),
            high=float(kline[2]),
            low=float(kline[3]),
            close=float(kline[4]),
            volume=float(kline[5]),
        )

    # --- Spot Market ---

    async def get_spot_klines(
        self, symbol: str, interval: str, limit: int
    ) -> list[KlineData]:
        """Fetch spot market klines."""
        url = f"{SPOT_BASE_URL}/api/v3/klines"
        params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
        data = await self._request(url, params)
        return [self._parse_kline(k) for k in data]

    async def get_spot_price(self, symbol: str) -> float:
        """Get current spot price."""
        url = f"{SPOT_BASE_URL}/api/v3/ticker/price"
        params = {"symbol": symbol.upper()}
        data = await self._request(url, params)
        return float(data["price"])

    async def get_all_spot_timeframes(
        self, symbol: str
    ) -> dict[str, list[KlineData]]:
        """Fetch all required timeframes for spot market."""
        tasks = {
            tf: self.get_spot_klines(symbol, cfg["interval"], cfg["limit"])
            for tf, cfg in TIMEFRAME_CONFIG.items()
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        
        data = {}
        for tf, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                raise BinanceAPIError(f"Failed to fetch {tf} klines: {result}")
            data[tf] = result
        
        return data

    # --- Perpetual Futures ---

    async def get_perp_klines(
        self, symbol: str, interval: str, limit: int
    ) -> list[KlineData]:
        """Fetch perpetual futures klines."""
        url = f"{FUTURES_BASE_URL}/fapi/v1/klines"
        params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
        data = await self._request(url, params)
        return [self._parse_kline(k) for k in data]

    async def get_perp_mark_price(self, symbol: str) -> float:
        """Get current perpetual mark price."""
        url = f"{FUTURES_BASE_URL}/fapi/v1/premiumIndex"
        params = {"symbol": symbol.upper()}
        data = await self._request(url, params)
        return float(data["markPrice"])

    async def get_funding_rate(self, symbol: str, limit: int = 8) -> list[FundingRateData]:
        """Get recent funding rates (last N 8-hour periods)."""
        url = f"{FUTURES_BASE_URL}/fapi/v1/fundingRate"
        params = {"symbol": symbol.upper(), "limit": limit}
        data = await self._request(url, params)
        return [
            FundingRateData(rate=float(item["fundingRate"]), timestamp=int(item["fundingTime"]))
            for item in data
        ]

    async def get_open_interest(self, symbol: str) -> OpenInterestData:
        """Get current open interest."""
        url = f"{FUTURES_BASE_URL}/fapi/v1/openInterest"
        params = {"symbol": symbol.upper()}
        data = await self._request(url, params)
        return OpenInterestData(
            value=float(data["openInterest"]),
            timestamp=int(data["time"]) if "time" in data else 0,
        )

    async def get_open_interest_hist(
        self, symbol: str, period: str = "1h", limit: int = 25
    ) -> list[dict[str, Any]]:
        """
        Get historical open interest series.

        Uses Binance Futures "data" endpoint, which returns a list of points including:
        - timestamp (ms)
        - sumOpenInterest (base asset amount, as string)
        """
        url = f"{FUTURES_BASE_URL}/futures/data/openInterestHist"
        params = {"symbol": symbol.upper(), "period": period, "limit": limit}
        data = await self._request(url, params)
        if not isinstance(data, list):
            raise BinanceAPIError("Unexpected openInterestHist response shape")
        return data

    @staticmethod
    def _calculate_oi_change_24h_pct_from_hist(hist: list[dict[str, Any]]) -> float:
        """Calculate (last - first) / first * 100 from OI history; returns 0.0 if unavailable."""
        points: list[tuple[int, float]] = []
        for item in hist:
            try:
                ts = int(item["timestamp"])
                oi = float(item["sumOpenInterest"])
            except Exception:
                continue
            points.append((ts, oi))

        if len(points) < 2:
            return 0.0

        points.sort(key=lambda x: x[0])
        first = points[0][1]
        last = points[-1][1]

        if first == 0.0:
            for _, oi in points:
                if oi != 0.0:
                    first = oi
                    break
            if first == 0.0:
                return 0.0

        return round(((last - first) / first) * 100.0, 2)

    async def get_24h_ticker(self, symbol: str, is_perp: bool = False) -> dict[str, Any]:
        """Get 24h ticker statistics."""
        if is_perp:
            url = f"{FUTURES_BASE_URL}/fapi/v1/ticker/24hr"
        else:
            url = f"{SPOT_BASE_URL}/api/v3/ticker/24hr"
        params = {"symbol": symbol.upper()}
        return await self._request(url, params)

    async def get_all_perp_timeframes(
        self, symbol: str
    ) -> dict[str, list[KlineData]]:
        """Fetch all required timeframes for perpetual futures."""
        tasks = {
            tf: self.get_perp_klines(symbol, cfg["interval"], cfg["limit"])
            for tf, cfg in TIMEFRAME_CONFIG.items()
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        
        data = {}
        for tf, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                raise BinanceAPIError(f"Failed to fetch {tf} klines: {result}")
            data[tf] = result
        
        return data

    async def get_perp_derivatives_data(
        self, symbol: str
    ) -> tuple[list[FundingRateData], OpenInterestData, float]:
        """Fetch all derivatives-specific data."""
        funding_task = self.get_funding_rate(symbol)
        oi_task = self.get_open_interest(symbol)
        oi_hist_task = self.get_open_interest_hist(symbol)
        
        results = await asyncio.gather(
            funding_task, oi_task, oi_hist_task, return_exceptions=True
        )
        
        # Funding + current OI are required; OI history is best-effort.
        if isinstance(results[0], Exception):
            raise BinanceAPIError(f"Failed to fetch funding rate: {results[0]}")
        if isinstance(results[1], Exception):
            raise BinanceAPIError(f"Failed to fetch open interest: {results[1]}")

        oi_change_24h_pct = 0.0
        if not isinstance(results[2], Exception):
            oi_change_24h_pct = self._calculate_oi_change_24h_pct_from_hist(results[2])  # type: ignore[arg-type]

        return results[0], results[1], oi_change_24h_pct  # type: ignore[return-value]

