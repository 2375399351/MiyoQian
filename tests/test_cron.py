from datetime import datetime
import unittest

from miyouqian.core.cron import CronExpression, validate_cron


class CronExpressionTests(unittest.TestCase):
    def test_next_occurrences(self):
        cases = [
            ("0 9 * * *", datetime(2026, 11, 22, 8, 59), datetime(2026, 11, 22, 9, 0)),
            ("*/30 * * * *", datetime(2026, 11, 22, 9, 31), datetime(2026, 11, 22, 10, 0)),
            ("0 9 * * 1-5", datetime(2026, 11, 22, 9, 0), datetime(2026, 11, 23, 9, 0)),
            ("0 0 1 * *", datetime(2026, 11, 22, 0, 0), datetime(2026, 12, 1, 0, 0)),
            ("0 8,20 * * *", datetime(2026, 11, 22, 9, 0), datetime(2026, 11, 22, 20, 0)),
            ("0 0 * * 7", datetime(2026, 11, 22, 0, 0), datetime(2026, 11, 29, 0, 0)),
            ("5/10 * * * *", datetime(2026, 11, 22, 9, 5), datetime(2026, 11, 22, 9, 15)),
        ]
        for expression, start, expected in cases:
            with self.subTest(expression=expression):
                self.assertEqual(CronExpression.parse(expression).next_after(start), expected)

    def test_invalid_expressions(self):
        for expression in ("", "* * * *", "60 * * * *", "0 24 * * *", "0 0 32 * *", "0 0 * 13 *", "0 0 * * 8", "abc * * * *"):
            with self.subTest(expression=expression):
                self.assertFalse(validate_cron(expression))


if __name__ == "__main__":
    unittest.main()
