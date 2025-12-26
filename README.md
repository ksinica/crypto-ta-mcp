# Crypto Technical Analysis MCP Server

An MCP (Model Context Protocol) server that fetches cryptocurrency market data from Binance and computes technical indicators for systematic analysis.

## Features

- **Multi-timeframe analysis**: Monthly, Weekly, and Daily data
- **Technical indicators**: Moving Averages, Bollinger Bands, ATR, Volume Analysis
- **Swing point detection**: Automated pivot/fractal detection
- **Market structure**: HH-HL, LH-LL, Range, Transition classification
- **Pattern recognition**:
  - **Candlestick patterns**: 15+ patterns including doji, hammer, engulfing, three white soldiers, etc.
  - **Swing patterns**: Head & Shoulders and Inverse Head & Shoulders with volume confirmation
- **Derivatives data**: Funding rates and Open Interest (perpetuals only)

## Installation

```bash
# Clone and navigate to the project
cd crypto-ta-mcp

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Running the Server

```bash
# Run via Python module (without installing)
PYTHONPATH=src python -m crypto_ta_mcp.server

# Or use the entry point after installing
pip install -e .
crypto-ta-mcp
```

### Running with Docker

```bash
# Build the image
docker build -t crypto-ta-mcp .

# Run the server
docker run -i crypto-ta-mcp
```

### MCP Configuration

Add to your MCP client configuration (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "crypto-ta": {
      "command": "python",
      "args": ["-m", "crypto_ta_mcp.server"],
      "cwd": "/path/to/crypto-ta-mcp/src"
    }
  }
}
```

Or if installed as a package:

```json
{
  "mcpServers": {
    "crypto-ta": {
      "command": "crypto-ta-mcp"
    }
  }
}
```

Or using Docker:

```json
{
  "mcpServers": {
    "crypto-ta": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "ghcr.io/ksinica/crypto-ta-mcp:latest"]
    }
  }
}
```

## Tools

### `fetch_spot_data`

Fetches spot market data and computes technical indicators.

**Parameters:**
- `symbol` (string, required): Trading pair symbol (e.g., `BTCUSDT`, `ETHUSDT`)
- `output_format` (string, optional): Output format - `json` (default, most token-efficient) or `yaml`

**Returns:** Complete technical analysis data including:
- OHLCV candles for Monthly, Weekly, and Daily timeframes
- Moving averages (10/20/50 monthly, 20/50/200 weekly & daily)
- Bollinger Bands (20-period, 2 std dev)
- ATR with regime classification
- Volume analysis relative to 20-period average
- Swing point detection
- **Candlestick patterns** (doji, hammer, engulfing, etc.)
- **Swing patterns** (Head & Shoulders, Inverse H&S with volume confirmation)
- Market structure and regime

**Output Format Options:**
- `json` - Compact JSON (default, most token-efficient for LLM consumption)
- `yaml` - YAML format (human-readable, good for review)

### `fetch_perp_data`

Fetches perpetual futures market data with derivatives metrics.

**Parameters:**
- `symbol` (string, required): Trading pair symbol (e.g., `BTCUSDT`, `ETHUSDT`)
- `output_format` (string, optional): Output format - `json` (default, most token-efficient) or `yaml`

**Returns:** Same as `fetch_spot_data`, plus:
- Current funding rate with trend analysis
- Open interest with 24h change

## Output Schema

The output is returned as a formatted string (JSON or YAML).

**Default Format:** Compact JSON (most token-efficient for LLM consumption)

Key sections in the output structure:

```yaml
meta:
  symbol: "BTCUSDT"
  venue: "Binance"
  market_type: "spot" | "perp"
  timezone: "UTC"
  candle_close: "00:00"
  as_of: "YYYY-MM-DD"

timeframes:
  monthly:
    candlestick_patterns: [...]  # Recent candlestick patterns
    swing_patterns: [...]  # Head & Shoulders, Inverse H&S
    regime: "bull" | "bear" | "neutral"
    structure: "HH-HL" | "LH-LL" | "range" | "transition"
    moving_averages: { values: { ma_10, ma_20, ma_50 }, notes }
    bollinger: { values, bandwidth, state, location }
    atr: { value, regime, percentile }
    volume: { current_vs_avg, interpretation }
    swing_points: [...]

  weekly: # Same structure with 20/50/200 MAs
  daily: # Same structure with 20/50/200 MAs

current_price: <latest price>

derivatives: # Only for fetch_perp_data
  funding_rate:
    current: <rate>
    trend: "positive" | "negative" | "neutral"
  open_interest:
    value: <OI>
    change_24h_pct: <percentage>
```

### Output Format Examples

**JSON (default - most token-efficient):**
```json
{"meta":{"symbol":"BTCUSDT",...},"timeframes":{...}}
```

**YAML (human-readable):**
```yaml
meta:
  symbol: BTCUSDT
  ...
timeframes:
  ...
```

## Data Sources

- **Spot Market**: Binance Public API (`api.binance.com`)
- **Perpetual Futures**: Binance Futures API (`fapi.binance.com`)

No API keys required - uses public endpoints only.

## Technical Details

### Timeframe Lookbacks

| Timeframe | Interval | Candles | Coverage |
|-----------|----------|---------|----------|
| Monthly | 1M | 60 | ~5 years |
| Weekly | 1w | 208 | ~4 years |
| Daily | 1d | 250 | ~1 year |

### Indicator Parameters

| Indicator | Parameter | Value |
|-----------|-----------|-------|
| Bollinger Bands | Period | 20 |
| Bollinger Bands | Std Dev | 2.0 |
| ATR | Period | 14 |
| Volume SMA | Period | 20 |
| Swing Points | Pivot N | 2 |

### Volume Classification

| Classification | Threshold |
|----------------|-----------|
| High | ≥1.5× average |
| Above Average | 1.2-1.5× |
| Average | 0.8-1.2× |
| Below Average | 0.5-0.8× |
| Low | <0.5× |

### ATR Regime

| Regime | Percentile |
|--------|------------|
| Low | <25th |
| Normal | 25th-75th |
| High | >75th |

### Pattern Detection

#### Candlestick Patterns (15+ patterns)
Detected on all timeframes with lookback of 10 candles:
- **Single candle**: Doji, Hammer, Inverted Hammer, Shooting Star, Hanging Man, Marubozu
- **Two candle**: Bullish/Bearish Engulfing, Bullish/Bearish Harami
- **Three candle**: Morning/Evening Star, Three White Soldiers, Three Black Crows

#### Swing Patterns (Multi-Swing Structures)
Detected using swing point analysis across the full timeframe:

**Head & Shoulders (Bearish Reversal)**
- Three-swing structure: left shoulder → head (higher) → right shoulder
- Neckline formed by intermediate lows
- Volume declining on right shoulder (quality indicator)
- Target: Pattern height projected from neckline break

**Inverse Head & Shoulders (Bullish Reversal)**
- Three-swing structure: left shoulder → head (lower) → right shoulder
- Neckline formed by intermediate highs
- Volume increasing on right shoulder (quality indicator)
- Target: Pattern height projected from neckline break

**Quality Assessment**:
- **Strong**: Clear structure + volume confirmation
- **Moderate**: Clear structure, volume neutral
- **Weak**: Structure present but volume contradicts

**Pattern Criteria**:
- Shoulder symmetry: within 2% price tolerance
- Clear neckline: identifiable support/resistance
- Volume behavior: assessed for quality rating
- Completion: pattern finalized on right shoulder formation

## License

MIT

