"""
Unit tests for calculator.
"""
import pytest
from calc import Calculator


class TestCalculator:
    """Test cases for Calculator class."""

    @pytest.fixture
    def calc(self):
        """Create calculator instance."""
        return Calculator()

    def test_add(self, calc):
        """Test addition operation."""
        assert calc.add(2, 3) == 5, "2 + 3 should equal 5"
        assert calc.add(0, 0) == 0, "0 + 0 should equal 0"
        assert calc.add(-1, 1) == 0, "-1 + 1 should equal 0"

    def test_subtract(self, calc):
        """Test subtraction operation."""
        assert calc.subtract(10, 4) == 6, "10 - 4 should equal 6"
        assert calc.subtract(5, 5) == 0, "5 - 5 should equal 0"

    def test_multiply(self, calc):
        """Test multiplication operation."""
        assert calc.multiply(5, 6) == 30, "5 * 6 should equal 30"
        assert calc.multiply(0, 100) == 0, "0 * 100 should equal 0"

    def test_divide(self, calc):
        """Test division operation."""
        assert calc.divide(20, 4) == 5.0, "20 / 4 should equal 5"
        with pytest.raises(ValueError):
            calc.divide(10, 0)
