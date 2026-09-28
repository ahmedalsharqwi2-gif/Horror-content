import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_script  # noqa: E402


class GenerateScriptTests(unittest.TestCase):
    def test_content_red_flag_checker_runs_and_detects_flag(self):
        self.assertIsNone(generate_script.find_content_red_flag("نص عربي سليم."))
        self.assertEqual(
            generate_script.find_content_red_flag("هذا البركان الثلجي غير موثق."),
            "البركان الثلجي",
        )


if __name__ == "__main__":
    unittest.main()
