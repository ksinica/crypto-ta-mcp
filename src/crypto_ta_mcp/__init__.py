"""Crypto Technical Analysis MCP Server."""

__version__ = "0.1.0"


def main() -> None:
    """Console entrypoint (lazy import to keep package import lightweight)."""
    from .server import main as _main

    _main()


__all__ = ["main", "__version__"]
