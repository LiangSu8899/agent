"""
Calculator application main entry point.
"""
from calc import Calculator


def main():
    """Main entry point."""
    calc = Calculator()

    # Test basic operations
    print("Calculator Test")
    print(f"2 + 3 = {calc.add(2, 3)}")  # Should be 5
    print(f"10 - 4 = {calc.subtract(10, 4)}")  # Should be 6
    print(f"5 * 6 = {calc.multiply(5, 6)}")  # Should be 30
    print(f"20 / 4 = {calc.divide(20, 4)}")  # Should be 5.0


if __name__ == "__main__":
    main()
