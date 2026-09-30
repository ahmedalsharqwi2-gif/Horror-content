import time
import unittest
from unittest.mock import patch

from scripts import llm_gateway
from scripts.llm_gateway import (
    OutputError,
    Provider,
    ProviderTimeout,
    _run_with_timeout,
    generate_valid_episode,
    make_validator,
    make_validator,
    parse_episode_json,
)


class LlmGatewayTests(unittest.TestCase):
    def test_short_episode_retry_includes_prior_narration_and_missing_words(self):
        short = {
            "title": "x", "hook": "هوك", "region": "مكان", "story_type": "true_case",
            "basis": "مصدر", "narration": "كلمة " * 10,
            "visual_keywords": ["night scene"] * 6,
            "caption": "قصة #رعب", "phonetic_hints": [],
        }
        full = dict(short, narration="كلمة " * 230)
        calls = []

        # Use JSON so parse_episode_json receives a real object.
        import json
        def json_provider(_system, user, _budget):
            calls.append(user)
            return json.dumps(short if len(calls) == 1 else full, ensure_ascii=False)

        episode, label = generate_valid_episode(
            "system", "request", 1000, [Provider("test", json_provider)],
            make_validator(), sleep=lambda _seconds: None,
        )
        self.assertEqual(label, "test")
        self.assertEqual(len(episode["narration"].split()), 230)
        self.assertIn("كلمة", calls[1])
        self.assertIn("أضف", calls[1])
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

    def test_build_providers_rotates_openrouter_models(self):
        with patch.object(llm_gateway, "GEMINI_API_KEY", ""), \
             patch.object(llm_gateway, "GROQ_API_KEY", ""), \
             patch.object(llm_gateway, "OPENROUTER_API_KEY", "test-key"), \
             patch.object(llm_gateway, "OPENROUTER_MODELS", ["model-a", "model-b"]):
            providers = llm_gateway.build_providers()
        self.assertEqual([p.label for p in providers], ["openrouter:model-a", "openrouter:model-b"])

    def test_blocking_provider_call_has_hard_timeout(self):
        with self.assertRaises(ProviderTimeout):
            _run_with_timeout(lambda: time.sleep(2), 1, "test-provider")


if __name__ == "__main__":
    unittest.main()
