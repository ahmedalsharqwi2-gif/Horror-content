import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.modules.setdefault("edge_tts", types.ModuleType("edge_tts"))

import generate_script  # noqa: E402
from generate_voice import normalize_min_min_pronunciation  # noqa: E402


class GenerateScriptTests(unittest.TestCase):
    def test_content_red_flag_checker_runs_and_detects_flag(self):
        self.assertIsNone(generate_script.find_content_red_flag("نص عربي سليم."))
        self.assertEqual(
            generate_script.find_content_red_flag("هذا البركان الثلجي غير موثق."),
            "البركان الثلجي",
        )

    def test_rejects_unanswered_question_as_final_sentence(self):
        self.assertTrue(generate_script.looks_open_ended("بدأت القصة هنا. ماذا حدث بعد ذلك؟"))
        self.assertFalse(generate_script.looks_open_ended("بدأت القصة هنا. ثم انطفأ الضوء وانتهى كل شيء."))

    def test_canonical_min_min_pronunciation(self):
        self.assertEqual(normalize_min_min_pronunciation("بحيرة مِينَ مِين"), "بحيرة مِين مِين")


if __name__ == "__main__":
    unittest.main()
