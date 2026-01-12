"""
Utility functions for calculator.
"""


def format_result(value):
    """Format calculation result."""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def validate_input(value):
    """Validate numeric input."""
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False
