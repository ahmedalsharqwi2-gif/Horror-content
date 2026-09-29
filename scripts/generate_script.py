"""Generate and validate one horror episode using the shared LLM gateway."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from arabic_guard import format_feedback, validate_narration
from llm_gateway import (
    EPISODE_SCHEMA,
    OutputError,
    WORDS_MAX,
    WORDS_MIN,
    generate_episode as gateway_generate_episode,
    make_validator,
)

SCRIPT_DIR = Path(__file__).parent
ROOT = SCRIPT_DIR.parent
PROMPT_PATH = ROOT / "prompts" / "horror_system_prompt.md"
OUTPUT_PATH = ROOT / "state" / "current_episode.json"
HISTORY_PATH = ROOT / "state" / "used_clips.json"
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "8"))
REGION_HISTORY_LIMIT = int(os.getenv("REGION_HISTORY_LIMIT", "6"))

CONTENT_RED_FLAGS = ("السيلينس", "الشهرات الجوية", "المحتلة بالدقيق", "البركان الثلجي")


def load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data.get("history", []) if isinstance(data, dict) else []


def load_used_history(limit: int = HISTORY_LIMIT) -> list[str]:
    return [x.get("title", "") for x in _history() if x.get("title")][-limit:]


def load_used_regions(limit: int = REGION_HISTORY_LIMIT) -> list[str]:
    return [x.get("region", "") for x in _history() if x.get("region")][-limit:]


def load_used_hooks(limit: int = HISTORY_LIMIT) -> list[str]:
    return [x.get("hook", "") for x in _history() if x.get("hook")][-limit:]


def find_content_red_flag(text: str) -> str | None:
    plain = re.sub(r"[\u064B-\u065F\u0670]", "", text or "")
    return next((flag for flag in CONTENT_RED_FLAGS if flag in plain), None)


def looks_truncated(narration: str) -> bool:
    stripped = narration.strip()
    return not stripped or not stripped.endswith((".", "!", "؟", "?", "…", '"', "”", "»"))


def to_gemini_schema(schema: dict) -> dict:
    """Convert the local JSON schema to the Gemini SDK's schema format."""
    result = {"type": schema["type"].upper()}
    if result["type"] == "OBJECT":
        result["properties"] = {
            key: to_gemini_schema(value)
            for key, value in schema.get("properties", {}).items()
        }
        if schema.get("required"):
            result["required"] = schema["required"]
    elif result["type"] == "ARRAY":
        result["items"] = to_gemini_schema(schema["items"])
    return result


def build_user_message(recent_titles: list[str], recent_regions: list[str], recent_hooks: list[str]) -> str:
    message = (
        "اكتب حلقة جديدة تمامًا، وأخرج كائن JSON واحدًا فقط.\n\n"
        "التزم بنمط story_type الذي سأحدده لك، وبقواعد اللغة الفصحى والرعب النفسي الموجودة في system prompt.\n"
        f"طول narration المطلوب من {WORDS_MIN} إلى {WORDS_MAX} كلمة.\n"
        "لا تكرر نفس الحادثة أو الفكرة أو المنطقة المذكورة في القوائم أدناه."
    )
    if recent_titles:
        message += "\n\nالعناوين السابقة:\n- " + "\n- ".join(recent_titles)
    if recent_hooks:
        message += "\n\nالهوكات/الحوادث السابقة:\n- " + "\n- ".join(recent_hooks)
    if recent_regions:
        message += "\n\nالمناطق السابقة:\n- " + "\n- ".join(recent_regions)
    return message


def validate_episode(episode: dict) -> None:
    """Project-specific checks layered on top of the gateway's structural checks."""
    narration = str(episode.get("narration", "")).strip()
    arabic_issues = validate_narration(narration)
    if arabic_issues:
        raise OutputError(format_feedback(arabic_issues))
    red_flag = find_content_red_flag(narration)
    if red_flag:
        raise OutputError(f"النص يحتوي مصطلحًا مرفوضًا: {red_flag}")
    if not str(episode.get("hook", "")).strip():
        raise OutputError("حقل hook فاضي")
    if not episode.get("visual_keywords"):
        raise OutputError("حقل visual_keywords فاضي")
    if looks_truncated(narration):
        raise OutputError("نص narration شكله متقطوع", truncated=True)


def generate_episode() -> dict:
    system_prompt = load_system_prompt()
    user_message = build_user_message(
        load_used_history(), load_used_regions(), load_used_hooks()
    )
    if not any(os.getenv(key, "").strip() for key in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY")):
        sys.exit("خطأ: أضف GEMINI_API_KEY أو GROQ_API_KEY أو OPENROUTER_API_KEY إلى GitHub Secrets")

    validator = make_validator(
        find_content_red_flag=find_content_red_flag,
        looks_truncated=looks_truncated,
    )

    def combined_validator(episode: dict) -> None:
        validator(episode)
        validate_episode(episode)

    budget = int(os.getenv("LLM_INITIAL_BUDGET", "6000"))
    print("🎬 بوابة التوليد: Gemini بالتتابع ثم Groq ثم OpenRouter")
    try:
        episode = gateway_generate_episode(
            system_prompt=system_prompt,
            budget=budget,
            validate=combined_validator,
            to_gemini_schema=to_gemini_schema,
            used_hooks=load_used_hooks(),
            recent_regions=load_used_regions(),
            rounds=int(os.getenv("LLM_ROUNDS", "2")),
            cooldown=int(os.getenv("LLM_ROUND_COOLDOWN", "30")),
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        raise SystemExit(f"❌ فشل توليد حلقة سليمة: {exc}") from exc
    return episode


if __name__ == "__main__":
    episode = generate_episode()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(episode, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ اتكتبت الحلقة: {episode['title']}")
    print(f"   النوع: {episode.get('story_type', 'غير محدد')}")
    print(f"   المنطقة: {episode.get('region', 'غير محدد')}")
    print(f"   الهوك: {episode.get('hook', '')[:80]}")
