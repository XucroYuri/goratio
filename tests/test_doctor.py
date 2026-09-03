import unittest

from goratio.doctor import run_doctor


class DoctorTests(unittest.TestCase):
    def test_all_modules_import(self) -> None:
        report = run_doctor()

        self.assertTrue(report["ok"])
        self.assertGreaterEqual(report["module_count"], 10)
        self.assertTrue(all(c["status"] == "ok" for c in report["checks"]))


if __name__ == "__main__":
    unittest.main()
