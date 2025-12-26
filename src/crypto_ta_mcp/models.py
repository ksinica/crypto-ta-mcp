"""Pydantic models for the Crypto TA MCP output schema."""

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MarketType(str, Enum):
    SPOT = "spot"
    PERP = "perp"


class Regime(str, Enum):
    BULL = "bull"
    BEAR = "bear"
    NEUTRAL = "neutral"


class Structure(str, Enum):
    HH_HL = "HH-HL"
    LH_LL = "LH-LL"
    RANGE = "range"
    TRANSITION = "transition"


class BollingerState(str, Enum):
    SQUEEZE = "squeeze"
    EXPANSION = "expansion"
    NORMAL = "normal"


class BollingerLocation(str, Enum):
    UPPER = "upper"
    MIDDLE = "middle"
    LOWER = "lower"
    OUTSIDE = "outside"


class ATRRegime(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class VolumeInterpretation(str, Enum):
    HIGH = "high"
    ABOVE_AVERAGE = "above_average"
    AVERAGE = "average"
    BELOW_AVERAGE = "below_average"
    LOW = "low"


class FundingTrend(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


# --- Candlestick Patterns ---


class CandlestickPatternType(str, Enum):
    """Types of candlestick patterns."""

    # Single candle patterns
    DOJI = "doji"
    HAMMER = "hammer"
    INVERTED_HAMMER = "inverted_hammer"
    SHOOTING_STAR = "shooting_star"
    HANGING_MAN = "hanging_man"
    MARUBOZU_BULL = "marubozu_bull"
    MARUBOZU_BEAR = "marubozu_bear"

    # Two candle patterns
    ENGULFING_BULL = "engulfing_bull"
    ENGULFING_BEAR = "engulfing_bear"
    HARAMI_BULL = "harami_bull"
    HARAMI_BEAR = "harami_bear"

    # Three candle patterns
    MORNING_STAR = "morning_star"
    EVENING_STAR = "evening_star"
    THREE_WHITE_SOLDIERS = "three_white_soldiers"
    THREE_BLACK_CROWS = "three_black_crows"


class PatternSignificance(str, Enum):
    """Significance/bias of a candlestick pattern."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class CandlestickPattern(BaseModel):
    """A detected candlestick pattern."""

    type: CandlestickPatternType
    timestamp: str = Field(description="ISO 8601 date (YYYY-MM-DD) of the pattern's final candle")
    significance: PatternSignificance


# --- Swing Patterns (Multi-Swing Structures) ---


class SwingPatternType(str, Enum):
    """Types of multi-swing patterns."""

    HEAD_AND_SHOULDERS = "head_and_shoulders"
    INVERSE_HEAD_AND_SHOULDERS = "inverse_head_and_shoulders"
    DOUBLE_TOP = "double_top"
    DOUBLE_BOTTOM = "double_bottom"
    TRIPLE_TOP = "triple_top"
    TRIPLE_BOTTOM = "triple_bottom"


class SwingPatternQuality(str, Enum):
    """Quality assessment of swing pattern."""

    STRONG = "strong"  # All criteria met including volume confirmation
    MODERATE = "moderate"  # Structure clear but volume not ideal
    WEAK = "weak"  # Structure present but some criteria questionable


class Neckline(BaseModel):
    """Neckline definition for H&S patterns."""

    price: float = Field(description="Average neckline price level")
    slope: str = Field(description="horizontal|ascending|descending")
    left_point: dict[str, float | str] = Field(description="Left neckline point {timestamp, price}")
    right_point: dict[str, float | str] = Field(description="Right neckline point {timestamp, price}")


class SwingPattern(BaseModel):
    """A detected multi-swing pattern (e.g., Head & Shoulders)."""

    type: SwingPatternType
    significance: PatternSignificance
    quality: SwingPatternQuality
    completion_timestamp: str = Field(description="ISO 8601 date when pattern completed")
    neckline: Optional[Neckline] = None
    target: Optional[float] = Field(
        default=None,
        description="Projected price target based on pattern height"
    )
    swing_points: list[dict[str, float | str]] = Field(
        description="Key swing points forming the pattern"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Additional context (e.g., 'volume declining on right shoulder')"
    )


# --- Moving Averages ---


class MonthlyMAValues(BaseModel):
    """Monthly moving average values."""

    ma_10: Optional[float] = None
    ma_20: Optional[float] = None
    ma_50: Optional[float] = None


class WeeklyMAValues(BaseModel):
    """Weekly moving average values."""

    ma_20: Optional[float] = None
    ma_50: Optional[float] = None
    ma_200: Optional[float] = None


class DailyMAValues(BaseModel):
    """Daily moving average values."""

    ma_20: Optional[float] = None
    ma_50: Optional[float] = None
    ma_200: Optional[float] = None


class MovingAverages(BaseModel):
    """Moving averages with optional notes."""

    values: MonthlyMAValues | WeeklyMAValues | DailyMAValues
    notes: Optional[str] = None


# --- Bollinger Bands ---


class BollingerValues(BaseModel):
    """Bollinger band values."""

    upper: float
    middle: float
    lower: float


class BollingerBands(BaseModel):
    """Bollinger Bands analysis."""

    period: int = 20
    std_dev: float = 2.0
    values: BollingerValues
    bandwidth: float = Field(description="(upper - lower) / middle")
    state: BollingerState
    location: BollingerLocation


# --- ATR ---


class ATR(BaseModel):
    """Average True Range analysis."""

    value: float
    regime: ATRRegime
    percentile: float = Field(description="Percentile vs 90-period lookback")


# --- Volume ---


class VolumeAnalysis(BaseModel):
    """Volume analysis."""

    current_vs_avg: float = Field(description="Ratio vs 20-period average")
    interpretation: VolumeInterpretation


# --- Swing Points ---


class SwingPoint(BaseModel):
    """A detected swing high or low."""

    timestamp: str = Field(description="ISO 8601 date (YYYY-MM-DD)")
    price: float
    type: str = Field(description="'high' or 'low'")


# --- Timeframe Data ---


class TimeframeData(BaseModel):
    """Complete data for a single timeframe."""

    candlestick_patterns: list[CandlestickPattern] = Field(default_factory=list)
    swing_patterns: list[SwingPattern] = Field(default_factory=list)
    regime: Regime
    structure: Structure
    moving_averages: MovingAverages
    bollinger: BollingerBands
    atr: ATR
    volume: VolumeAnalysis
    swing_points: list[SwingPoint] = Field(default_factory=list)


# --- Derivatives ---


class FundingRate(BaseModel):
    """Funding rate data for perpetuals."""

    current: float
    trend: FundingTrend


class OpenInterest(BaseModel):
    """Open interest data for perpetuals."""

    value: float = Field(description="OI in base currency")
    change_24h_pct: float


class DerivativesData(BaseModel):
    """Derivatives-specific data."""

    funding_rate: FundingRate
    open_interest: OpenInterest


# --- Timeframes Container ---


class Timeframes(BaseModel):
    """All timeframe data."""

    monthly: TimeframeData
    weekly: TimeframeData
    daily: TimeframeData


# --- Meta ---


class Meta(BaseModel):
    """Metadata about the analysis."""

    symbol: str
    venue: str = "Binance"
    market_type: MarketType
    timezone: str = "UTC"
    candle_close: str = "00:00"
    as_of: str


# --- Main Response Models ---


class SpotDataResponse(BaseModel):
    """Response for fetch_spot_data tool."""

    meta: Meta
    timeframes: Timeframes
    current_price: float


class PerpDataResponse(BaseModel):
    """Response for fetch_perp_data tool."""

    meta: Meta
    timeframes: Timeframes
    current_price: float
    derivatives: DerivativesData


# --- Chain TVL Response ---


class TVLChangeData(BaseModel):
    """TVL change percentages over different time periods."""

    change_1d_pct: Optional[float] = Field(default=None, description="TVL change in last 24 hours (%)")
    change_7d_pct: Optional[float] = Field(default=None, description="TVL change in last 7 days (%)")
    change_1m_pct: Optional[float] = Field(default=None, description="TVL change in last 30 days (%)")


class ChainTVLResponse(BaseModel):
    """Response for fetch_chain_tvl tool."""

    chain: str = Field(description="Blockchain name")
    tvl: float = Field(description="Total Value Locked in USD")
    tvl_change: TVLChangeData = Field(description="TVL change percentages")
    token_symbol: Optional[str] = Field(default=None, description="Native token symbol")
    chain_id: Optional[int] = Field(default=None, description="EVM chain ID if applicable")
    stables_mcap: Optional[float] = Field(default=None, description="Stablecoins market cap on chain (USD)")
    active_addresses_24h: Optional[int] = Field(default=None, description="Active addresses in last 24h")
    app_revenue_24h: Optional[float] = Field(default=None, description="Total app revenue in last 24h (USD)")
    nft_volume_24h: Optional[float] = Field(default=None, description="NFT trading volume in last 24h (USD)")
    bridged_tvl: Optional[float] = Field(default=None, description="TVL bridged to other chains (USD)")
    as_of: str = Field(description="Timestamp of the data")

