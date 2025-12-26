"""Output formatting utilities for different serialization formats."""

import json
import re
from enum import Enum
from typing import Any

import yaml


class OutputFormat:
    """Valid output format types."""
    
    JSON = "json"
    YAML = "yaml"
    
    @classmethod
    def all(cls) -> list[str]:
        """Return all valid format options."""
        return [cls.JSON, cls.YAML]
    
    @classmethod
    def validate(cls, format_str: str) -> bool:
        """Check if format string is valid."""
        return format_str in cls.all()


def _remove_scientific_notation(json_str: str) -> str:
    """
    Post-process JSON string to convert scientific notation to decimal format.
    
    Converts patterns like 3.88e-06 to 0.00000388 for better readability.
    """
    def replace_scientific(match):
        num_str = match.group(0)
        try:
            num = float(num_str)
            # Format with high precision, remove trailing zeros
            formatted = format(num, '.15f').rstrip('0').rstrip('.')
            return formatted
        except:
            return num_str
    
    # Pattern matches scientific notation: -?\d+\.?\d*[eE][+-]?\d+
    pattern = r'-?\d+\.?\d*[eE][+-]?\d+'
    return re.sub(pattern, replace_scientific, json_str)


def _prepare_for_serialization(data: Any) -> Any:
    """
    Recursively prepare data for serialization by converting enums to strings
    and ensuring floats are properly formatted (no scientific notation).
    """
    if isinstance(data, dict):
        return {key: _prepare_for_serialization(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [_prepare_for_serialization(item) for item in data]
    elif isinstance(data, Enum):
        return data.value
    else:
        return data


def format_output(data: dict[str, Any], format_type: str) -> str:
    """
    Format output data according to the specified format.
    
    Args:
        data: Dictionary data to format (typically from Pydantic model_dump())
        format_type: Output format - "json" or "yaml"
    
    Returns:
        Formatted string representation of the data
    
    Raises:
        ValueError: If format_type is not valid
    """
    if not OutputFormat.validate(format_type):
        raise ValueError(
            f"Invalid output format '{format_type}'. "
            f"Must be one of: {', '.join(OutputFormat.all())}"
        )
    
    # Ensure data is fully serializable
    prepared_data = _prepare_for_serialization(data)
    
    if format_type == OutputFormat.JSON:
        # Compact JSON, avoid scientific notation for readability
        json_str = json.dumps(prepared_data, separators=(',', ':'))
        return _remove_scientific_notation(json_str)
    
    elif format_type == OutputFormat.YAML:
        # YAML format - human-readable, good for review
        return yaml.dump(
            prepared_data,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )
    
    # Should never reach here due to validation above
    raise ValueError(f"Unhandled format type: {format_type}")

