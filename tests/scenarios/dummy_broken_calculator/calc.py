"""
Core calculator logic with intentional bug.
BUG: The add function returns subtraction instead of addition.
"""


class Calculator:
    """Simple calculator class."""

    def add(self, a, b):
        """Add two numbers - INTENTIONAL BUG: returns subtraction."""
        return a - b  # BUG: Should be a + b

    def subtract(self, a, b):
        """Subtract two numbers."""
        return a - b

    def multiply(self, a, b):
        """Multiply two numbers."""
        return a * b

    def divide(self, a, b):
        """Divide two numbers."""
        if b == 0:
            raise ValueError("Division by zero")
        return a / b
