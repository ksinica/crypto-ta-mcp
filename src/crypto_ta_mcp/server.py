"""FastMCP server for Crypto Technical Analysis."""

from datetime import date, timezone, datetime

from mcp.server.fastmcp import FastMCP

from .binance import BinanceClient, BinanceAPIError, FundingRateData
from .formatters import format_output, OutputFormat
from .indicators import process_timeframe
from .models import (
    DerivativesData,
    FundingRate,
    FundingTrend,
    MarketType,
    Meta,
    OpenInterest,
    PerpDataResponse,
    SpotDataResponse,
    Timeframes,
)

# Initialize FastMCP server
mcp = FastMCP(
    name="crypto-ta",
    instructions="Crypto Technical Analysis MCP Server - Provides structured market data for systematic crypto analysis",
)


def get_current_date() -> str:
    """Get current date in YYYY-MM-DD format (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def determine_funding_trend(funding_rates: list[FundingRateData]) -> FundingTrend:
    """Determine funding rate trend from recent history."""
    if len(funding_rates) < 2:
        return FundingTrend.NEUTRAL
    
    # Get rates in chronological order
    rates = [fr.rate for fr in sorted(funding_rates, key=lambda x: x.timestamp)]
    
    # Calculate average of first half vs second half
    mid = len(rates) // 2
    first_half_avg = sum(rates[:mid]) / mid if mid > 0 else 0
    second_half_avg = sum(rates[mid:]) / (len(rates) - mid) if len(rates) > mid else 0
    
    # Also consider absolute values
    latest = rates[-1]
    
    # Threshold for significance
    threshold = 0.0001  # 0.01%
    
    if latest > threshold and second_half_avg > first_half_avg:
        return FundingTrend.POSITIVE
    elif latest < -threshold and second_half_avg < first_half_avg:
        return FundingTrend.NEGATIVE
    else:
        return FundingTrend.NEUTRAL


@mcp.tool()
async def fetch_spot_data(symbol: str, output_format: str = "json") -> str:
    """
    Fetch spot market data and compute technical indicators for a given symbol.
    
    Args:
        symbol: Trading pair symbol (e.g., BTCUSDT, ETHUSDT)
        output_format: Output format - "json" (default, most token-efficient) or "yaml"
    
    Returns:
        Complete technical analysis data including OHLCV candles for Monthly, Weekly,
        and Daily timeframes, computed indicators (MAs, Bollinger Bands, ATR, Volume),
        swing point detection, and current price position.
        
        Output is returned as a formatted string in the specified format.
    """
    # Validate format first
    if not OutputFormat.validate(output_format):
        return format_output(
            {
                "error": f"Invalid output format '{output_format}'. Must be one of: {', '.join(OutputFormat.all())}",
                "symbol": symbol
            },
            OutputFormat.JSON
        )
    
    try:
        async with BinanceClient() as client:
            # Fetch all data in parallel
            klines_data = await client.get_all_spot_timeframes(symbol)
            current_price = await client.get_spot_price(symbol)
        
        # Process each timeframe
        monthly_data = process_timeframe(klines_data["monthly"], "monthly")
        weekly_data = process_timeframe(klines_data["weekly"], "weekly")
        daily_data = process_timeframe(klines_data["daily"], "daily")
        
        # Build response
        response = SpotDataResponse(
            meta=Meta(
                symbol=symbol.upper(),
                market_type=MarketType.SPOT,
                as_of=get_current_date(),
            ),
            timeframes=Timeframes(
                monthly=monthly_data,
                weekly=weekly_data,
                daily=daily_data,
            ),
            current_price=round(current_price, 6),
        )
        
        return format_output(response.model_dump(), output_format)
    
    except BinanceAPIError as e:
        return format_output({"error": str(e), "symbol": symbol}, output_format)
    except Exception as e:
        return format_output({"error": f"Unexpected error: {e}", "symbol": symbol}, output_format)


@mcp.tool()
async def fetch_perp_data(symbol: str, output_format: str = "json") -> str:
    """
    Fetch perpetual futures market data with derivatives-specific metrics.
    
    Args:
        symbol: Trading pair symbol (e.g., BTCUSDT, ETHUSDT)
        output_format: Output format - "json" (default, most token-efficient) or "yaml"
    
    Returns:
        Complete technical analysis data including OHLCV candles for Monthly, Weekly,
        and Daily timeframes, computed indicators (MAs, Bollinger Bands, ATR, Volume),
        swing point detection, current price, plus derivatives data (funding rate,
        open interest).
        
        Output is returned as a formatted string in the specified format.
    """
    # Validate format first
    if not OutputFormat.validate(output_format):
        return format_output(
            {
                "error": f"Invalid output format '{output_format}'. Must be one of: {', '.join(OutputFormat.all())}",
                "symbol": symbol
            },
            OutputFormat.JSON
        )
    
    try:
        async with BinanceClient() as client:
            # Fetch all data in parallel
            klines_data = await client.get_all_perp_timeframes(symbol)
            current_price = await client.get_perp_mark_price(symbol)
            funding_rates, oi_data, oi_change_24h_pct = await client.get_perp_derivatives_data(symbol)
        
        # Process each timeframe
        monthly_data = process_timeframe(klines_data["monthly"], "monthly")
        weekly_data = process_timeframe(klines_data["weekly"], "weekly")
        daily_data = process_timeframe(klines_data["daily"], "daily")
        
        # Determine funding trend
        funding_trend = determine_funding_trend(funding_rates)
        current_funding = funding_rates[-1].rate if funding_rates else 0.0
        
        # Build derivatives data
        derivatives = DerivativesData(
            funding_rate=FundingRate(
                current=round(current_funding, 8),  # 8 decimals to avoid scientific notation
                trend=funding_trend,
            ),
            open_interest=OpenInterest(
                value=round(oi_data.value, 2),
                change_24h_pct=round(oi_change_24h_pct, 2),
            ),
        )
        
        # Build response
        response = PerpDataResponse(
            meta=Meta(
                symbol=symbol.upper(),
                market_type=MarketType.PERP,
                as_of=get_current_date(),
            ),
            timeframes=Timeframes(
                monthly=monthly_data,
                weekly=weekly_data,
                daily=daily_data,
            ),
            current_price=round(current_price, 6),
            derivatives=derivatives,
        )
        
        return format_output(response.model_dump(), output_format)
    
    except BinanceAPIError as e:
        return format_output({"error": str(e), "symbol": symbol}, output_format)
    except Exception as e:
        return format_output({"error": f"Unexpected error: {e}", "symbol": symbol}, output_format)


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()

