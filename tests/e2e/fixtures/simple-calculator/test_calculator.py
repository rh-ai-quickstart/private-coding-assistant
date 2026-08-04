"""Stdlib unittest suite for the simple calculator.

Power cases are included so the e2e agent only needs to implement power()
in calculator.py (power is intentionally missing from the fixture).
"""

import unittest

from calculator import add, divide, multiply, subtract


class TestCalculator(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)

    def test_subtract(self):
        self.assertEqual(subtract(5, 2), 3)

    def test_multiply(self):
        self.assertEqual(multiply(3, 4), 12)

    def test_divide(self):
        self.assertEqual(divide(10, 2), 5)

    def test_divide_by_zero(self):
        with self.assertRaises(ValueError):
            divide(1, 0)

    def test_power_two_to_the_four(self):
        from calculator import power

        self.assertEqual(power(2, 4), 16)

    def test_power_three_squared(self):
        from calculator import power

        self.assertEqual(power(3, 2), 9)


if __name__ == "__main__":
    unittest.main()
