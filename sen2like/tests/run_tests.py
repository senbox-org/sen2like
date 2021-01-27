import os
import unittest

try:
    from HtmlTestRunner import HTMLTestRunner

    runner = HTMLTestRunner(combine_reports=True, output="reports/tests", report_name="sen2like_tests_report",
                            failfast=False, verbosity=2)
except ImportError:
    runner = unittest.TextTestRunner(verbosity=2)

if __name__ == '__main__':
    suite = unittest.TestLoader().discover(os.path.dirname(__file__), pattern='test_*.py')
    runner.run(suite)
