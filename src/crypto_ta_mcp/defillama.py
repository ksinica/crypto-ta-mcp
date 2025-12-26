"""DefiLlama API client for fetching DeFi TVL data."""

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx

# Base URLs
DEFILLAMA_BASE_URL = "https://api.llama.fi"
STABLECOINS_BASE_URL = "https://stablecoins.llama.fi"

# Retry configuration
RETRYABLE_STATUS_CODES: set[int] = {429, 500, 502, 503, 504}
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE_SECONDS = 0.5
DEFAULT_BACKOFF_MAX_SECONDS = 8.0


@dataclass
class TVLChange:
    """TVL change percentages."""

    change_1d: float | None = None
    change_7d: float | None = None
    change_1m: float | None = None


@dataclass
class ChainTVLData:
    """Comprehensive TVL and metrics data for a blockchain."""

    name: str
    tvl: float
    tvl_change: TVLChange = field(default_factory=TVLChange)
    token_symbol: str | None = None
    chain_id: int | None = None
    # Additional metrics
    stables_mcap: float | None = None
    active_addresses_24h: int | None = None
    app_revenue_24h: float | None = None
    nft_volume_24h: float | None = None
    bridged_tvl: float | None = None


class DefiLlamaAPIError(Exception):
    """Custom exception for DefiLlama API errors."""

    pass


class DefiLlamaClient:
    """Async client for DefiLlama API."""

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

    async def __aenter__(self) -> "DefiLlamaClient":
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
                    text = response.text
                    snippet = text[:500] + ("..." if len(text) > 500 else "")
                    raise DefiLlamaAPIError(f"Non-JSON response from DefiLlama: {snippet}") from e

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

                raise DefiLlamaAPIError(f"HTTP error {status}: {e.response.text}") from e

            except (httpx.TimeoutException, httpx.RequestError) as e:
                last_error = e

                if attempt < self.max_retries:
                    delay = min(self.backoff_base_seconds * (2**attempt), self.backoff_max_seconds)
                    await asyncio.sleep(delay)
                    continue

                raise DefiLlamaAPIError(f"Request failed: {e}") from e

        raise DefiLlamaAPIError(f"Request failed after retries: {last_error}") from last_error

    async def _request_optional(self, url: str, params: dict[str, Any] | None = None) -> Any | None:
        """Make an HTTP GET request, returning None on error instead of raising."""
        try:
            return await self._request(url, params)
        except DefiLlamaAPIError:
            return None

    # --- Core TVL Data ---

    async def get_all_chains_tvl(self) -> list[dict[str, Any]]:
        """Fetch TVL for all chains."""
        url = f"{DEFILLAMA_BASE_URL}/v2/chains"
        return await self._request(url)

    # --- Stablecoins ---

    async def get_stablecoins_chains(self) -> list[dict[str, Any]]:
        """Fetch stablecoin market cap data per chain."""
        url = f"{STABLECOINS_BASE_URL}/stablecoinchains"
        return await self._request_optional(url) or []

    # --- Active Users ---

    async def get_active_users(self) -> dict[str, Any]:
        """Fetch active users/addresses data."""
        url = f"{DEFILLAMA_BASE_URL}/activeUsers"
        return await self._request_optional(url) or {}

    # --- Fees/Revenue ---

    async def get_fees_overview(self, chain: str) -> dict[str, Any] | None:
        """Fetch fees/revenue overview for a chain."""
        url = f"{DEFILLAMA_BASE_URL}/overview/fees/{chain}"
        params = {"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true"}
        return await self._request_optional(url, params)

    # --- NFT Volume ---

    async def get_nft_volume_chains(self) -> list[dict[str, Any]]:
        """Fetch NFT volume data per chain."""
        url = f"{DEFILLAMA_BASE_URL}/overview/nfts"
        params = {"excludeTotalDataChart": "true", "excludeTotalDataChartBreakdown": "true"}
        data = await self._request_optional(url, params)
        if data and isinstance(data, dict):
            return data.get("allChains", [])
        return []

    # --- Historical TVL ---

    async def get_historical_chain_tvl(self, chain: str) -> list[dict[str, Any]]:
        """Fetch historical TVL data for a chain."""
        url = f"{DEFILLAMA_BASE_URL}/v2/historicalChainTvl/{chain}"
        return await self._request_optional(url) or []

    # --- Main Method ---

    async def get_chain_tvl(self, chain: str) -> ChainTVLData:
        """
        Get comprehensive TVL and metrics for a specific chain.

        Args:
            chain: Chain name (e.g., "Ethereum", "Solana", "Arbitrum")

        Returns:
            ChainTVLData with TVL, change percentages, and additional metrics

        Raises:
            DefiLlamaAPIError: If chain not found or API error
        """
        # Fetch all data in parallel
        chains_task = self.get_all_chains_tvl()
        stables_task = self.get_stablecoins_chains()
        users_task = self.get_active_users()
        nft_task = self.get_nft_volume_chains()

        results = await asyncio.gather(
            chains_task, stables_task, users_task, nft_task,
            return_exceptions=True
        )

        # Unpack results
        chains_data = results[0] if not isinstance(results[0], Exception) else []
        stables_data = results[1] if not isinstance(results[1], Exception) else []
        users_data = results[2] if not isinstance(results[2], Exception) else {}
        nft_data = results[3] if not isinstance(results[3], Exception) else []

        if not chains_data:
            raise DefiLlamaAPIError("Failed to fetch chains data")

        # Find the chain (case-insensitive)
        chain_lower = chain.lower()
        chain_info = None

        for c in chains_data:
            c_name = c.get("name") or ""
            if c_name.lower() == chain_lower:
                chain_info = c
                break

        # Try partial match if exact match fails
        if chain_info is None:
            for c in chains_data:
                c_name = c.get("name") or ""
                if chain_lower in c_name.lower():
                    chain_info = c
                    break

        if chain_info is None:
            available_chains = sorted([c.get("name") or "" for c in chains_data if c.get("name")])[:20]
            raise DefiLlamaAPIError(
                f"Chain '{chain}' not found. Some available chains: {', '.join(available_chains)}..."
            )

        chain_name = chain_info.get("name") or chain
        chain_name_lower = chain_name.lower()
        current_tvl = self._safe_float(chain_info.get("tvl")) or 0.0

        # Extract TVL change data - try multiple possible field names
        # The API might use different field names, so we'll try common variations
        tvl_change = TVLChange(
            change_1d=self._safe_float(
                chain_info.get("change_1d") or 
                chain_info.get("change1d") or 
                chain_info.get("change_24h") or
                chain_info.get("change24h")
            ),
            change_7d=self._safe_float(
                chain_info.get("change_7d") or 
                chain_info.get("change7d")
            ),
            change_1m=self._safe_float(
                chain_info.get("change_1m") or 
                chain_info.get("change1m") or
                chain_info.get("change_30d") or
                chain_info.get("change30d")
            ),
        )

        # If we didn't get change data from the main API, try historical data
        if tvl_change.change_1d is None or tvl_change.change_7d is None or tvl_change.change_1m is None:
            historical_data = await self.get_historical_chain_tvl(chain_name)
            if historical_data:
                calculated_changes = self._calculate_tvl_changes(historical_data, current_tvl)
                # Use calculated values only if the original was None
                if tvl_change.change_1d is None:
                    tvl_change.change_1d = calculated_changes.change_1d
                if tvl_change.change_7d is None:
                    tvl_change.change_7d = calculated_changes.change_7d
                if tvl_change.change_1m is None:
                    tvl_change.change_1m = calculated_changes.change_1m

        # Find stablecoins market cap for this chain
        stables_mcap = None
        for s in stables_data:
            s_name = (s.get("name") or "").lower()
            s_gecko = (s.get("gecko_id") or "").lower()
            if s_name == chain_name_lower or s_gecko == chain_name_lower:
                stables_mcap = self._safe_float((s.get("totalCirculatingUSD") or {}).get("peggedUSD"))
                break

        # Find active addresses for this chain
        active_addresses = None
        if isinstance(users_data, dict):
            # The API returns chain data in various formats, try to find our chain
            for key, value in users_data.items():
                if (key or "").lower() == chain_name_lower:
                    if isinstance(value, dict):
                        active_addresses = self._safe_int(value.get("users"))
                    elif isinstance(value, (int, float)):
                        active_addresses = int(value)
                    break

        # Find NFT volume for this chain
        nft_volume = None
        for n in nft_data:
            if isinstance(n, dict):
                nft_chain = (n.get("chain") or "").lower()
                if nft_chain == chain_name_lower:
                    nft_volume = self._safe_float(n.get("total24h"))
                    break
            elif isinstance(n, str) and n.lower() == chain_name_lower:
                # Some responses just list chain names
                pass

        # Fetch fees/revenue for this chain (separate call needed)
        fees_data = await self.get_fees_overview(chain_name)
        app_revenue = None
        if fees_data and isinstance(fees_data, dict):
            app_revenue = self._safe_float(fees_data.get("total24h"))

        return ChainTVLData(
            name=chain_name,
            tvl=current_tvl,
            tvl_change=tvl_change,
            token_symbol=chain_info.get("tokenSymbol"),
            chain_id=self._safe_int(chain_info.get("chainId")),
            stables_mcap=stables_mcap,
            active_addresses_24h=active_addresses,
            app_revenue_24h=app_revenue,
            nft_volume_24h=nft_volume,
            bridged_tvl=self._safe_float(chain_info.get("bridgedTo")),
        )

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        """Safely convert value to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        """Safely convert value to int."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _calculate_tvl_changes(historical_data: list[dict[str, Any]], current_tvl: float) -> TVLChange:
        """
        Calculate TVL percentage changes from historical data.
        
        Args:
            historical_data: List of historical TVL data points with 'date' and 'tvl' fields
            current_tvl: Current TVL value
            
        Returns:
            TVLChange with calculated percentage changes
        """
        if not historical_data or current_tvl == 0:
            return TVLChange()
        
        # Sort by date (timestamp) in descending order
        sorted_data = sorted(historical_data, key=lambda x: x.get("date", 0), reverse=True)
        
        # Current time in seconds
        import time
        now = time.time()
        
        # Time deltas in seconds
        one_day = 86400  # 24 * 60 * 60
        seven_days = 604800  # 7 * 24 * 60 * 60
        thirty_days = 2592000  # 30 * 24 * 60 * 60
        
        changes = TVLChange()
        
        # Find TVL values at specific time intervals
        for entry in sorted_data:
            timestamp = entry.get("date", 0)
            tvl = entry.get("tvl", 0)
            
            if tvl and tvl > 0:
                time_diff = now - timestamp
                
                # 1-day change
                if changes.change_1d is None and abs(time_diff - one_day) < 3600:  # Within 1 hour
                    changes.change_1d = ((current_tvl - tvl) / tvl) * 100
                
                # 7-day change
                if changes.change_7d is None and abs(time_diff - seven_days) < 7200:  # Within 2 hours
                    changes.change_7d = ((current_tvl - tvl) / tvl) * 100
                
                # 30-day change
                if changes.change_1m is None and abs(time_diff - thirty_days) < 86400:  # Within 1 day
                    changes.change_1m = ((current_tvl - tvl) / tvl) * 100
                
                # Break if we have all values
                if all([changes.change_1d, changes.change_7d, changes.change_1m]):
                    break
        
        return changes
