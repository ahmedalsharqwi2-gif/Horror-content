import unittest

from scripts.llm_gateway import OutputError, make_validator, parse_episode_json


class LlmGatewayTests(unittest.TestCase):
    def test_parse_episode_json_removes_fence_and_think_block(self):
        raw = '<think>internal</think>\n```json\n{"title": "x"}\n```'
        self.assertEqual(parse_episode_json(raw), {"title": "x"})

    def test_parse_episode_json_rejects_truncated_json(self):
        with self.assertRaises(OutputError) as ctx:
            parse_episode_json('{"title": "x"')
        self.assertTrue(ctx.exception.truncated)

    def test_validator_rejects_sci_fi_without_fiction_caption(self):
        episode = {
            "title": "اختبار",
            "hook": "في عام 2090 وصلت إشارة قبل إرسالها",
            "region": "الفضاء",
            "story_type": "sci_fi",
            "basis": "الاتصالات الراديوية",
            "narration": " ".join(["إشارة"] * 230) + ".",
            "visual_keywords": ["radio station night"] * 6,
            "caption": "قصة رعب #رعب",
            "phonetic_hints": [],
        }
        with self.assertRaises(OutputError):
            make_validator()(episode)


if __name__ == "__main__":
    unittest.main()
