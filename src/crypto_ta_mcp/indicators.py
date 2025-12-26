"""Technical indicator calculations."""

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .binance import KlineData
from .models import (
    ATR,
    ATRRegime,
    BollingerBands,
    BollingerLocation,
    BollingerState,
    BollingerValues,
    CandlestickPattern,
    CandlestickPatternType,
    DailyMAValues,
    MonthlyMAValues,
    MovingAverages,
    Neckline,
    PatternSignificance,
    Regime,
    Structure,
    SwingPattern,
    SwingPatternQuality,
    SwingPatternType,
    SwingPoint,
    TimeframeData,
    VolumeAnalysis,
    VolumeInterpretation,
    WeeklyMAValues,
)


def klines_to_dataframe(klines: list[KlineData]) -> pd.DataFrame:
    """Convert klines to a pandas DataFrame."""
    df = pd.DataFrame(
        {
            "timestamp": [k.timestamp for k in klines],
            "open": [k.open for k in klines],
            "high": [k.high for k in klines],
            "low": [k.low for k in klines],
            "close": [k.close for k in klines],
            "volume": [k.volume for k in klines],
        }
    )
    return df


def _timestamp_to_iso(timestamp_ms: int) -> str:
    """Convert Unix timestamp in milliseconds to date string (YYYY-MM-DD)."""
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


# --- Candlestick Pattern Detection ---


def _body_size(o: float, c: float) -> float:
    """Calculate absolute body size."""
    return abs(c - o)


def _upper_wick(o: float, h: float, c: float) -> float:
    """Calculate upper wick size."""
    return h - max(o, c)


def _lower_wick(o: float, l: float, c: float) -> float:
    """Calculate lower wick size."""
    return min(o, c) - l


def _is_bullish(o: float, c: float) -> bool:
    """Check if candle is bullish."""
    return c > o


def _is_bearish(o: float, c: float) -> bool:
    """Check if candle is bearish."""
    return c < o


def detect_candlestick_patterns(
    df: pd.DataFrame, lookback: int = 10
) -> list[CandlestickPattern]:
    """Detect candlestick patterns in recent candles.
    
    Args:
        df: DataFrame with OHLCV data
        lookback: Number of recent candles to analyze for patterns
    
    Returns:
        List of detected patterns, most recent first
    """
    patterns: list[CandlestickPattern] = []
    
    if len(df) < 3:
        return patterns
    
    # Analyze only recent candles for efficiency
    start_idx = max(0, len(df) - lookback)
    
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    timestamps = df["timestamp"].values
    
    # Calculate average body size for relative comparisons
    body_sizes = np.abs(closes - opens)
    avg_body = float(np.mean(body_sizes[-50:])) if len(body_sizes) >= 50 else float(np.mean(body_sizes))
    
    for i in range(start_idx, len(df)):
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        ts = _timestamp_to_iso(int(timestamps[i]))
        
        body = _body_size(o, c)
        upper = _upper_wick(o, h, c)
        lower = _lower_wick(o, l, c)
        candle_range = h - l
        
        if candle_range == 0:
            continue
        
        # --- Single Candle Patterns ---
        
        # Doji: very small body relative to range
        if body < candle_range * 0.1:
            patterns.append(CandlestickPattern(
                type=CandlestickPatternType.DOJI,
                timestamp=ts,
                significance=PatternSignificance.NEUTRAL,
            ))
            continue
        
        # Marubozu: body is almost the entire candle (no/tiny wicks)
        if body > candle_range * 0.9:
            if _is_bullish(o, c):
                patterns.append(CandlestickPattern(
                    type=CandlestickPatternType.MARUBOZU_BULL,
                    timestamp=ts,
                    significance=PatternSignificance.BULLISH,
                ))
            else:
                patterns.append(CandlestickPattern(
                    type=CandlestickPatternType.MARUBOZU_BEAR,
                    timestamp=ts,
                    significance=PatternSignificance.BEARISH,
                ))
            continue
        
        # Hammer / Hanging Man: small body at top, long lower wick
        if (
            body < candle_range * 0.35
            and lower > body * 2
            and upper < body * 0.5
        ):
            # Hammer if at potential bottom (bullish), Hanging Man if at top (bearish)
            # We'll mark based on body color for simplicity
            if _is_bullish(o, c):
                patterns.append(CandlestickPattern(
                    type=CandlestickPatternType.HAMMER,
                    timestamp=ts,
                    significance=PatternSignificance.BULLISH,
                ))
            else:
                patterns.append(CandlestickPattern(
                    type=CandlestickPatternType.HANGING_MAN,
                    timestamp=ts,
                    significance=PatternSignificance.BEARISH,
                ))
            continue
        
        # Inverted Hammer / Shooting Star: small body at bottom, long upper wick
        if (
            body < candle_range * 0.35
            and upper > body * 2
            and lower < body * 0.5
        ):
            if _is_bullish(o, c):
                patterns.append(CandlestickPattern(
                    type=CandlestickPatternType.INVERTED_HAMMER,
                    timestamp=ts,
                    significance=PatternSignificance.BULLISH,
                ))
            else:
                patterns.append(CandlestickPattern(
                    type=CandlestickPatternType.SHOOTING_STAR,
                    timestamp=ts,
                    significance=PatternSignificance.BEARISH,
                ))
            continue
        
        # --- Two Candle Patterns (need previous candle) ---
        if i < 1:
            continue
            
        prev_o, prev_h, prev_l, prev_c = opens[i-1], highs[i-1], lows[i-1], closes[i-1]
        prev_body = _body_size(prev_o, prev_c)
        
        # Engulfing patterns
        if (
            prev_body > avg_body * 0.3  # Previous candle has meaningful body
            and body > prev_body * 1.1   # Current body engulfs previous
        ):
            # Bullish engulfing: prev bearish, current bullish, current body covers prev
            if (
                _is_bearish(prev_o, prev_c)
                and _is_bullish(o, c)
                and c > prev_o
                and o < prev_c
            ):
                patterns.append(CandlestickPattern(
                    type=CandlestickPatternType.ENGULFING_BULL,
                    timestamp=ts,
                    significance=PatternSignificance.BULLISH,
                ))
                continue
            
            # Bearish engulfing: prev bullish, current bearish, current body covers prev
            if (
                _is_bullish(prev_o, prev_c)
                and _is_bearish(o, c)
                and c < prev_o
                and o > prev_c
            ):
                patterns.append(CandlestickPattern(
                    type=CandlestickPatternType.ENGULFING_BEAR,
                    timestamp=ts,
                    significance=PatternSignificance.BEARISH,
                ))
                continue
        
        # Harami patterns (inside bar)
        if (
            prev_body > avg_body * 0.5  # Previous candle has large body
            and body < prev_body * 0.5   # Current body is small
        ):
            # Bullish harami: prev bearish, current bullish small inside
            if (
                _is_bearish(prev_o, prev_c)
                and _is_bullish(o, c)
                and c < prev_o
                and o > prev_c
            ):
                patterns.append(CandlestickPattern(
                    type=CandlestickPatternType.HARAMI_BULL,
                    timestamp=ts,
                    significance=PatternSignificance.BULLISH,
                ))
                continue
            
            # Bearish harami: prev bullish, current bearish small inside
            if (
                _is_bullish(prev_o, prev_c)
                and _is_bearish(o, c)
                and c > prev_o
                and o < prev_c
            ):
                patterns.append(CandlestickPattern(
                    type=CandlestickPatternType.HARAMI_BEAR,
                    timestamp=ts,
                    significance=PatternSignificance.BEARISH,
                ))
                continue
        
        # --- Three Candle Patterns ---
        if i < 2:
            continue
            
        prev2_o, prev2_c = opens[i-2], closes[i-2]
        prev2_body = _body_size(prev2_o, prev2_c)
        
        # Three White Soldiers: three consecutive bullish candles with higher closes
        if (
            _is_bullish(prev2_o, prev2_c)
            and _is_bullish(prev_o, prev_c)
            and _is_bullish(o, c)
            and prev_c > prev2_c
            and c > prev_c
            and prev2_body > avg_body * 0.5
            and prev_body > avg_body * 0.5
            and body > avg_body * 0.5
        ):
            patterns.append(CandlestickPattern(
                type=CandlestickPatternType.THREE_WHITE_SOLDIERS,
                timestamp=ts,
                significance=PatternSignificance.BULLISH,
            ))
            continue
        
        # Three Black Crows: three consecutive bearish candles with lower closes
        if (
            _is_bearish(prev2_o, prev2_c)
            and _is_bearish(prev_o, prev_c)
            and _is_bearish(o, c)
            and prev_c < prev2_c
            and c < prev_c
            and prev2_body > avg_body * 0.5
            and prev_body > avg_body * 0.5
            and body > avg_body * 0.5
        ):
            patterns.append(CandlestickPattern(
                type=CandlestickPatternType.THREE_BLACK_CROWS,
                timestamp=ts,
                significance=PatternSignificance.BEARISH,
            ))
            continue
        
        # Morning Star: bearish, small body (doji-like), bullish
        middle_body = prev_body
        middle_range = prev_h - prev_l
        if (
            _is_bearish(prev2_o, prev2_c)
            and prev2_body > avg_body * 0.5  # First candle large bearish
            and middle_body < middle_range * 0.3 if middle_range > 0 else False  # Middle small
            and _is_bullish(o, c)
            and body > avg_body * 0.5  # Third candle large bullish
            and c > (prev2_o + prev2_c) / 2  # Close above midpoint of first
        ):
            patterns.append(CandlestickPattern(
                type=CandlestickPatternType.MORNING_STAR,
                timestamp=ts,
                significance=PatternSignificance.BULLISH,
            ))
            continue
        
        # Evening Star: bullish, small body (doji-like), bearish
        if (
            _is_bullish(prev2_o, prev2_c)
            and prev2_body > avg_body * 0.5  # First candle large bullish
            and middle_body < middle_range * 0.3 if middle_range > 0 else False  # Middle small
            and _is_bearish(o, c)
            and body > avg_body * 0.5  # Third candle large bearish
            and c < (prev2_o + prev2_c) / 2  # Close below midpoint of first
        ):
            patterns.append(CandlestickPattern(
                type=CandlestickPatternType.EVENING_STAR,
                timestamp=ts,
                significance=PatternSignificance.BEARISH,
            ))
            continue
    
    # Return patterns sorted by timestamp (most recent last)
    patterns.sort(key=lambda p: p.timestamp)
    return patterns


# --- Swing Pattern Detection (Head & Shoulders, Double Tops/Bottoms) ---


def detect_head_and_shoulders(
    swings: list[SwingPoint],
    df: pd.DataFrame,
    tolerance_pct: float = 0.02
) -> list[SwingPattern]:
    """Detect Head & Shoulders and Inverse Head & Shoulders patterns.
    
    Args:
        swings: List of swing points (highs and lows)
        df: DataFrame with OHLCV + volume data for volume confirmation
        tolerance_pct: Price tolerance for shoulder symmetry (default 2%)
    
    Returns:
        List of detected H&S patterns
    
    Criteria per framework.md Section 7, line 614:
    - Clear three-swing structure
    - Neckline identifiable
    - Volume declining on right shoulder (quality factor)
    """
    patterns: list[SwingPattern] = []
    
    if len(swings) < 5:
        return patterns
    
    # Separate highs and lows
    highs = [s for s in swings if s.type == "high"]
    lows = [s for s in swings if s.type == "low"]
    
    # --- Classic Head & Shoulders (Bearish at Top) ---
    # Pattern: left shoulder (high), head (higher high), right shoulder (high ~= left)
    # With lows forming neckline
    
    if len(highs) >= 3 and len(lows) >= 2:
        for i in range(len(highs) - 2):
            left_shoulder = highs[i]
            head = highs[i + 1]
            right_shoulder = highs[i + 2]
            
            # Head must be the highest point
            if head.price <= left_shoulder.price or head.price <= right_shoulder.price:
                continue
            
            # Shoulders should be roughly symmetrical (within tolerance)
            shoulder_diff_pct = abs(left_shoulder.price - right_shoulder.price) / left_shoulder.price
            if shoulder_diff_pct > tolerance_pct:
                continue
            
            # Right shoulder should be lower than left (classic pattern)
            # or roughly equal - allow some flexibility
            if right_shoulder.price > left_shoulder.price * 1.05:
                continue
            
            # Find neckline: lows between left shoulder and right shoulder
            # Get timestamps to find intermediate lows
            left_time = left_shoulder.timestamp
            right_time = right_shoulder.timestamp
            
            intermediate_lows = [
                low for low in lows
                if left_time < low.timestamp < right_time
            ]
            
            if len(intermediate_lows) < 1:
                continue
            
            # Neckline: use the first and last intermediate low to define it
            if len(intermediate_lows) == 1:
                # Need at least 2 points for a neckline; look for lows around head
                continue
            
            left_neck = intermediate_lows[0]
            right_neck = intermediate_lows[-1]
            
            # Calculate neckline slope
            neckline_price = (left_neck.price + right_neck.price) / 2
            slope_pct = (right_neck.price - left_neck.price) / left_neck.price
            
            if abs(slope_pct) < 0.01:
                slope = "horizontal"
            elif slope_pct > 0:
                slope = "ascending"
            else:
                slope = "descending"
            
            # Volume analysis: check if volume is declining on right shoulder
            volume_quality = _assess_hs_volume_quality(
                df,
                left_shoulder.timestamp,
                head.timestamp,
                right_shoulder.timestamp,
                "bearish"
            )
            
            # Calculate target: pattern height from head to neckline, projected down
            pattern_height = head.price - neckline_price
            target = neckline_price - pattern_height
            
            # Build pattern
            pattern = SwingPattern(
                type=SwingPatternType.HEAD_AND_SHOULDERS,
                significance=PatternSignificance.BEARISH,
                quality=volume_quality,
                completion_timestamp=right_shoulder.timestamp,
                neckline=Neckline(
                    price=round(neckline_price, 6),
                    slope=slope,
                    left_point={"timestamp": left_neck.timestamp, "price": left_neck.price},
                    right_point={"timestamp": right_neck.timestamp, "price": right_neck.price},
                ),
                target=round(target, 6),
                swing_points=[
                    {"timestamp": left_shoulder.timestamp, "price": left_shoulder.price, "label": "left_shoulder"},
                    {"timestamp": head.timestamp, "price": head.price, "label": "head"},
                    {"timestamp": right_shoulder.timestamp, "price": right_shoulder.price, "label": "right_shoulder"},
                ],
                notes=f"Neckline at {neckline_price:.2f}; volume {volume_quality.value} on right shoulder"
            )
            
            patterns.append(pattern)
    
    # --- Inverse Head & Shoulders (Bullish at Bottom) ---
    # Pattern: left shoulder (low), head (lower low), right shoulder (low ~= left)
    # With highs forming neckline
    
    if len(lows) >= 3 and len(highs) >= 2:
        for i in range(len(lows) - 2):
            left_shoulder = lows[i]
            head = lows[i + 1]
            right_shoulder = lows[i + 2]
            
            # Head must be the lowest point
            if head.price >= left_shoulder.price or head.price >= right_shoulder.price:
                continue
            
            # Shoulders should be roughly symmetrical
            shoulder_diff_pct = abs(left_shoulder.price - right_shoulder.price) / left_shoulder.price
            if shoulder_diff_pct > tolerance_pct:
                continue
            
            # Right shoulder should be higher than left (classic pattern)
            # or roughly equal
            if right_shoulder.price < left_shoulder.price * 0.95:
                continue
            
            # Find neckline: highs between left shoulder and right shoulder
            left_time = left_shoulder.timestamp
            right_time = right_shoulder.timestamp
            
            intermediate_highs = [
                high for high in highs
                if left_time < high.timestamp < right_time
            ]
            
            if len(intermediate_highs) < 1:
                continue
            
            if len(intermediate_highs) == 1:
                continue
            
            left_neck = intermediate_highs[0]
            right_neck = intermediate_highs[-1]
            
            # Calculate neckline
            neckline_price = (left_neck.price + right_neck.price) / 2
            slope_pct = (right_neck.price - left_neck.price) / left_neck.price
            
            if abs(slope_pct) < 0.01:
                slope = "horizontal"
            elif slope_pct > 0:
                slope = "ascending"
            else:
                slope = "descending"
            
            # Volume analysis
            volume_quality = _assess_hs_volume_quality(
                df,
                left_shoulder.timestamp,
                head.timestamp,
                right_shoulder.timestamp,
                "bullish"
            )
            
            # Calculate target: pattern height projected up
            pattern_height = neckline_price - head.price
            target = neckline_price + pattern_height
            
            pattern = SwingPattern(
                type=SwingPatternType.INVERSE_HEAD_AND_SHOULDERS,
                significance=PatternSignificance.BULLISH,
                quality=volume_quality,
                completion_timestamp=right_shoulder.timestamp,
                neckline=Neckline(
                    price=round(neckline_price, 6),
                    slope=slope,
                    left_point={"timestamp": left_neck.timestamp, "price": left_neck.price},
                    right_point={"timestamp": right_neck.timestamp, "price": right_neck.price},
                ),
                target=round(target, 6),
                swing_points=[
                    {"timestamp": left_shoulder.timestamp, "price": left_shoulder.price, "label": "left_shoulder"},
                    {"timestamp": head.timestamp, "price": head.price, "label": "head"},
                    {"timestamp": right_shoulder.timestamp, "price": right_shoulder.price, "label": "right_shoulder"},
                ],
                notes=f"Neckline at {neckline_price:.2f}; volume {volume_quality.value} on right shoulder"
            )
            
            patterns.append(pattern)
    
    return patterns


def _assess_hs_volume_quality(
    df: pd.DataFrame,
    left_shoulder_ts: str,
    head_ts: str,
    right_shoulder_ts: str,
    pattern_type: str
) -> SwingPatternQuality:
    """Assess volume quality for H&S pattern.
    
    Per framework: volume should decline on right shoulder (bearish)
    or increase on right shoulder (bullish for inverse H&S).
    
    Args:
        df: DataFrame with volume data
        left_shoulder_ts: Timestamp of left shoulder
        head_ts: Timestamp of head
        right_shoulder_ts: Timestamp of right shoulder
        pattern_type: "bearish" or "bullish"
    
    Returns:
        Quality rating based on volume behavior
    """
    # Convert timestamps to find corresponding volume
    volumes = df["volume"].values
    timestamps = df["timestamp"].values
    
    # Find indices (approximate - match by timestamp)
    try:
        # Convert ISO strings to timestamps for comparison
        from datetime import datetime
        left_idx = None
        head_idx = None
        right_idx = None
        
        for idx, ts in enumerate(timestamps):
            ts_str = _timestamp_to_iso(int(ts))
            if ts_str == left_shoulder_ts:
                left_idx = idx
            elif ts_str == head_ts:
                head_idx = idx
            elif ts_str == right_shoulder_ts:
                right_idx = idx
        
        if left_idx is None or head_idx is None or right_idx is None:
            return SwingPatternQuality.MODERATE
        
        # Calculate average volume at each swing
        # Use small window around each swing point
        window = 3
        left_vol = float(np.mean(volumes[max(0, left_idx-window):left_idx+window+1]))
        head_vol = float(np.mean(volumes[max(0, head_idx-window):head_idx+window+1]))
        right_vol = float(np.mean(volumes[max(0, right_idx-window):right_idx+window+1]))
        
        if pattern_type == "bearish":
            # For bearish H&S: declining volume on right shoulder is strong
            if right_vol < head_vol * 0.7 and right_vol < left_vol * 0.8:
                return SwingPatternQuality.STRONG
            elif right_vol < head_vol:
                return SwingPatternQuality.MODERATE
            else:
                return SwingPatternQuality.WEAK
        else:
            # For bullish inverse H&S: increasing volume on right shoulder is strong
            if right_vol > head_vol * 1.2 and right_vol > left_vol:
                return SwingPatternQuality.STRONG
            elif right_vol > head_vol * 0.9:
                return SwingPatternQuality.MODERATE
            else:
                return SwingPatternQuality.WEAK
                
    except Exception:
        # If volume analysis fails, return moderate quality
        return SwingPatternQuality.MODERATE


# --- Moving Averages ---


def calculate_sma(series: pd.Series, period: int) -> float | None:
    """Calculate Simple Moving Average, return latest value."""
    if len(series) < period:
        return None
    return round(float(series.tail(period).mean()), 6)


def calculate_moving_averages(
    df: pd.DataFrame, timeframe: str
) -> MovingAverages:
    """Calculate moving averages for a given timeframe."""
    close = df["close"]
    
    if timeframe == "monthly":
        values = MonthlyMAValues(
            ma_10=calculate_sma(close, 10),
            ma_20=calculate_sma(close, 20),
            ma_50=calculate_sma(close, 50),
        )
    elif timeframe == "weekly":
        values = WeeklyMAValues(
            ma_20=calculate_sma(close, 20),
            ma_50=calculate_sma(close, 50),
            ma_200=calculate_sma(close, 200),
        )
    else:  # daily
        values = DailyMAValues(
            ma_20=calculate_sma(close, 20),
            ma_50=calculate_sma(close, 50),
            ma_200=calculate_sma(close, 200),
        )
    
    # Generate notes
    current_price = float(close.iloc[-1])
    notes_parts = []
    
    if timeframe == "monthly":
        if values.ma_10 is not None:
            if current_price > values.ma_10:
                notes_parts.append("price above 10M")
            else:
                notes_parts.append("price below 10M")
        if values.ma_20 is not None:
            if current_price > values.ma_20:
                notes_parts.append("above 20M")
            else:
                notes_parts.append("below 20M")
        if values.ma_50 is not None:
            if current_price > values.ma_50:
                notes_parts.append("above 50M")
            else:
                notes_parts.append("below 50M")
    elif timeframe == "weekly":
        if values.ma_20 is not None:
            if current_price > values.ma_20:
                notes_parts.append("price above 20W")
            else:
                notes_parts.append("price below 20W")
        if values.ma_50 is not None:
            if current_price > values.ma_50:
                notes_parts.append("above 50W")
            else:
                notes_parts.append("below 50W")
        if values.ma_200 is not None:
            if current_price > values.ma_200:
                notes_parts.append("above 200W")
            else:
                notes_parts.append("below 200W")
    else:  # daily
        if values.ma_20 is not None:
            if current_price > values.ma_20:
                notes_parts.append("price above 20D")
            else:
                notes_parts.append("price below 20D")
        if values.ma_50 is not None:
            if current_price > values.ma_50:
                notes_parts.append("above 50D")
            else:
                notes_parts.append("below 50D")
        if values.ma_200 is not None:
            if current_price > values.ma_200:
                notes_parts.append("above 200D")
            else:
                notes_parts.append("below 200D")
    
    notes = "; ".join(notes_parts) if notes_parts else None
    
    return MovingAverages(values=values, notes=notes)


# --- Bollinger Bands ---


def calculate_bollinger_bands(
    df: pd.DataFrame, period: int = 20, std_dev: float = 2.0
) -> BollingerBands:
    """Calculate Bollinger Bands."""
    close = df["close"]
    current_price = float(close.iloc[-1])
    
    # Calculate bands
    middle = float(close.tail(period).mean())
    std = float(close.tail(period).std())
    upper = round(middle + (std_dev * std), 6)
    lower = round(middle - (std_dev * std), 6)
    middle = round(middle, 6)
    
    # Bandwidth
    bandwidth = (upper - lower) / middle if middle > 0 else 0
    
    # Calculate bandwidth percentile for squeeze detection
    # Roll through the series to get historical bandwidths
    rolling_mean = close.rolling(window=period).mean()
    rolling_std = close.rolling(window=period).std()
    historical_upper = rolling_mean + (std_dev * rolling_std)
    historical_lower = rolling_mean - (std_dev * rolling_std)
    historical_bandwidth = (historical_upper - historical_lower) / rolling_mean
    
    # Get percentile (last 100 periods for comparison)
    lookback = min(100, len(historical_bandwidth.dropna()))
    recent_bandwidths = historical_bandwidth.dropna().tail(lookback)
    
    if len(recent_bandwidths) > 0:
        current_percentile = (recent_bandwidths < bandwidth).mean() * 100
        if current_percentile < 20:
            state = BollingerState.SQUEEZE
        elif current_percentile > 80:
            state = BollingerState.EXPANSION
        else:
            state = BollingerState.NORMAL
    else:
        state = BollingerState.NORMAL
    
    # Determine location
    if current_price > upper:
        location = BollingerLocation.OUTSIDE
    elif current_price >= middle + (upper - middle) * 0.5:
        location = BollingerLocation.UPPER
    elif current_price <= middle - (middle - lower) * 0.5:
        location = BollingerLocation.LOWER
    else:
        location = BollingerLocation.MIDDLE
    
    return BollingerBands(
        period=period,
        std_dev=std_dev,
        values=BollingerValues(upper=upper, middle=middle, lower=lower),
        bandwidth=round(bandwidth, 4),
        state=state,
        location=location,
    )


# --- ATR ---


def calculate_true_range(df: pd.DataFrame) -> pd.Series:
    """Calculate True Range for each candle."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> ATR:
    """Calculate Average True Range with regime classification."""
    tr = calculate_true_range(df)
    
    # Calculate ATR (simple moving average of TR)
    atr_series = tr.rolling(window=period).mean()
    current_atr = float(atr_series.iloc[-1])
    
    # Calculate percentile vs 90-period lookback
    lookback = 90
    recent_atr = atr_series.dropna().tail(lookback)
    
    if len(recent_atr) > 0:
        percentile = float((recent_atr < current_atr).mean() * 100)
    else:
        percentile = 50.0
    
    # Determine regime based on percentile
    if percentile < 25:
        regime = ATRRegime.LOW
    elif percentile > 75:
        regime = ATRRegime.HIGH
    else:
        regime = ATRRegime.NORMAL
    
    return ATR(value=round(current_atr, 2), regime=regime, percentile=round(percentile, 1))


# --- Volume Analysis ---


def calculate_volume_analysis(df: pd.DataFrame, period: int = 20) -> VolumeAnalysis:
    """Calculate volume analysis relative to moving average."""
    volume = df["volume"]
    current_volume = float(volume.iloc[-1])
    
    # Calculate average
    if len(volume) >= period:
        avg_volume = float(volume.tail(period).mean())
    else:
        avg_volume = float(volume.mean())
    
    # Calculate ratio
    ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
    
    # Classify
    if ratio >= 1.5:
        interpretation = VolumeInterpretation.HIGH
    elif ratio >= 1.2:
        interpretation = VolumeInterpretation.ABOVE_AVERAGE
    elif ratio >= 0.8:
        interpretation = VolumeInterpretation.AVERAGE
    elif ratio >= 0.5:
        interpretation = VolumeInterpretation.BELOW_AVERAGE
    else:
        interpretation = VolumeInterpretation.LOW
    
    return VolumeAnalysis(
        current_vs_avg=round(ratio, 2), interpretation=interpretation
    )


# --- Swing Points ---


def detect_swing_points(df: pd.DataFrame, n: int = 2) -> list[SwingPoint]:
    """Detect swing highs and lows using pivot/fractal method."""
    swings = []
    highs = df["high"].values
    lows = df["low"].values
    timestamps = df["timestamp"].values
    
    # Need at least 2n+1 candles
    if len(df) < 2 * n + 1:
        return swings
    
    for i in range(n, len(df) - n):
        # Check for swing high
        is_swing_high = True
        for j in range(1, n + 1):
            if highs[i] <= highs[i - j] or highs[i] <= highs[i + j]:
                is_swing_high = False
                break
        
        if is_swing_high:
            swings.append(
                SwingPoint(timestamp=_timestamp_to_iso(int(timestamps[i])), price=round(float(highs[i]), 6), type="high")
            )
        
        # Check for swing low
        is_swing_low = True
        for j in range(1, n + 1):
            if lows[i] >= lows[i - j] or lows[i] >= lows[i + j]:
                is_swing_low = False
                break
        
        if is_swing_low:
            swings.append(
                SwingPoint(timestamp=_timestamp_to_iso(int(timestamps[i])), price=round(float(lows[i]), 6), type="low")
            )
    
    # Sort by timestamp
    swings.sort(key=lambda x: x.timestamp)
    return swings


# --- Structure Detection ---


def determine_structure(swings: list[SwingPoint]) -> Structure:
    """Determine market structure from swing points."""
    if len(swings) < 4:
        return Structure.TRANSITION
    
    # Get last 4-6 swing points
    recent = swings[-6:] if len(swings) >= 6 else swings[-4:]
    
    # Separate highs and lows
    highs = [s for s in recent if s.type == "high"]
    lows = [s for s in recent if s.type == "low"]
    
    if len(highs) < 2 or len(lows) < 2:
        return Structure.TRANSITION
    
    # Check for higher highs and higher lows
    last_two_highs = highs[-2:]
    last_two_lows = lows[-2:]
    
    hh = last_two_highs[1].price > last_two_highs[0].price
    hl = last_two_lows[1].price > last_two_lows[0].price
    lh = last_two_highs[1].price < last_two_highs[0].price
    ll = last_two_lows[1].price < last_two_lows[0].price
    
    if hh and hl:
        return Structure.HH_HL
    elif lh and ll:
        return Structure.LH_LL
    else:
        # Range detection: if swing highs and lows are relatively flat (within tolerance),
        # treat as a range rather than "transition".
        #
        # The previous implementation required exact float equality, making RANGE
        # practically unreachable.
        high_prices = [h.price for h in highs[-3:]] if len(highs) >= 3 else [h.price for h in highs]
        low_prices = [l.price for l in lows[-3:]] if len(lows) >= 3 else [l.price for l in lows]
        if len(high_prices) >= 2 and len(low_prices) >= 2:
            high_range_pct = (max(high_prices) - min(high_prices)) / max(high_prices) if max(high_prices) else 0.0
            low_range_pct = (max(low_prices) - min(low_prices)) / max(low_prices) if max(low_prices) else 0.0

            # 1% tolerance is a pragmatic default for "flat" swing levels across crypto.
            tol = 0.01
            if high_range_pct <= tol and low_range_pct <= tol:
                return Structure.RANGE

        return Structure.TRANSITION


# --- Regime Detection ---


def determine_regime(df: pd.DataFrame, structure: Structure, timeframe: str) -> Regime:
    """Determine market regime based on structure and MA position."""
    close = df["close"]
    current_price = float(close.iloc[-1])
    
    # Get relevant MAs
    if timeframe == "monthly":
        ma_periods = [10, 20]
    elif timeframe == "weekly":
        ma_periods = [20, 50]
    else:
        ma_periods = [20, 50]
    
    above_ma_count = 0
    below_ma_count = 0
    
    for period in ma_periods:
        if len(close) >= period:
            ma_value = float(close.tail(period).mean())
            if current_price > ma_value:
                above_ma_count += 1
            else:
                below_ma_count += 1
    
    # Combine structure and MA position
    if structure == Structure.HH_HL and above_ma_count >= below_ma_count:
        return Regime.BULL
    elif structure == Structure.LH_LL and below_ma_count >= above_ma_count:
        return Regime.BEAR
    elif structure in (Structure.RANGE, Structure.TRANSITION):
        return Regime.NEUTRAL
    elif above_ma_count > below_ma_count:
        return Regime.BULL
    elif below_ma_count > above_ma_count:
        return Regime.BEAR
    else:
        return Regime.NEUTRAL


# --- Main Processing Function ---


def process_timeframe(klines: list[KlineData], timeframe: str) -> TimeframeData:
    """Process all indicators for a single timeframe."""
    df = klines_to_dataframe(klines)
    
    # Calculate all indicators
    moving_averages = calculate_moving_averages(df, timeframe)
    bollinger = calculate_bollinger_bands(df)
    atr = calculate_atr(df)
    volume = calculate_volume_analysis(df)
    swing_points = detect_swing_points(df, n=2)
    structure = determine_structure(swing_points)
    regime = determine_regime(df, structure, timeframe)
    
    # Detect candlestick patterns in recent candles
    candlestick_patterns = detect_candlestick_patterns(df, lookback=10)
    
    # Detect swing patterns (Head & Shoulders, etc.)
    swing_patterns = detect_head_and_shoulders(swing_points, df, tolerance_pct=0.02)
    
    return TimeframeData(
        candlestick_patterns=candlestick_patterns,
        swing_patterns=swing_patterns,
        regime=regime,
        structure=structure,
        moving_averages=moving_averages,
        bollinger=bollinger,
        atr=atr,
        volume=volume,
        swing_points=swing_points,
    )

