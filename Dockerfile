FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY pyproject.toml .
COPY README.md .
COPY src/ src/

# Install the package
RUN pip install --no-cache-dir .

# Run the MCP server
CMD ["crypto-ta-mcp"]
