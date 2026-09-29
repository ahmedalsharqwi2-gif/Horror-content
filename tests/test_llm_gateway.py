import unittest

from scripts.llm_gateway import OutputError, make_validator, parse_episode_json


def valid_episode():
    return {
        "title": "إشارة سبقت إرسالها",
        "hook": "في عام ٢٠٩٠ وصلت إشارة قبل إرسالها",
        "region": "محطة قطبية",
        "story_type": "sci_fi",
        "basis": "الاتصالات الراديوية",
        "narration": " ".join(["إشارة"] * 230) + " نهاية.",
        "visual_keywords": ["radio station night"] * 7,
        "caption": "قصة خيالية عن إشارة غامضة. #خيال_علمي #رعب",
        "phonetic_hints": [],
    }


class LlmGatewayTests(unittest.TestCase):
    def test_parse_episode_json_removes_fence_and_think_block(self):
        raw = '<think>internal</think>\n```json\n{"title": "x"}\n```'
        self.assertEqual(parse_episode_json(raw), {"title": "x"})

    def test_parse_episode_json_rejects_truncated_json(self):
        with self.assertRaises(OutputError) as ctx:
            parse_episode_json('{"title": "x"')
        self.assertTrue(ctx.exception.truncated)

    def test_validator_rejects_sci_fi_without_fiction_caption(self):
        episode = valid_episode()
        episode["caption"] = "قصة رعب #رعب"
        with self.assertRaises(OutputError):
            make_validator()(episode)

    def test_validator_rejects_foreign_scripts_in_arabic_narration(self):
        for fragment in (
            "waveform", "extérieure", "entonces", "חזרה", "这一次", "ループ",
        ):
            with self.subTest(fragment=fragment):
                episode = valid_episode()
                episode["narration"] = " ".join(["إشارة"] * 230) + f" {fragment} نهاية."
                with self.assertRaisesRegex(OutputError, "narration.*لغات أخرى"):
                    make_validator()(episode)

    def test_arabic_metadata_is_checked_but_english_visual_keywords_are_allowed(self):
        episode = valid_episode()
        make_validator()(episode)
        episode["title"] += " waveform"
        with self.assertRaisesRegex(OutputError, "title.*لغات أخرى"):
            make_validator()(episode)

    def test_foreign_letters_in_phonetic_hints_are_rejected(self):
        episode = valid_episode()
        episode["narration"] = " ".join(["إشارة"] * 230) + " يلو نايف."
        episode["phonetic_hints"] = [{"word": "يلو نايف", "phonetic": "Yellowknife"}]
        with self.assertRaisesRegex(OutputError, "phonetic_hints.phonetic.*غير عربية"):
            make_validator()(episode)


if __name__ == "__main__":
    unittest.main()
