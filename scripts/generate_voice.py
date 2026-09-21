"""توليد صوت الحلقة كاملة وترجمة ASS متزامنة.

هذا الملف لا يقسم القصة إلى أجزاء. ينتج:
- downloaded_clips/narration_voice.mp3
- downloaded_clips/narration_with_music.mp3
- downloaded_clips/narration.ass
ويحدّث current_episode.json بالمسارات الجديدة.
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

import edge_tts

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
STATE_DIR = ROOT_DIR / "state"
CLIPS_DIR = ROOT_DIR / "downloaded_clips"
ASSETS_DIR = ROOT_DIR / "assets"
EPISODE_PATH = STATE_DIR / "current_episode.json"
BACKGROUND_MUSIC = ASSETS_DIR / "background_music.mp3"

VOICE = "ar-EG-ShakirNeural"
RATE = "-15%"
PITCH = "-9Hz"
VOLUME = "+0%"
MUSIC_VOLUME = 0.15
WORDS_PER_CAPTION_CHUNK = 4
VIDEO_W = 1920
VIDEO_H = 1080

VOICE_AUDIO = CLIPS_DIR / "narration_voice.mp3"
FINAL_AUDIO = CLIPS_DIR / "narration_with_music.mp3"
SUBTITLES = CLIPS_DIR / "narration.ass"

PAUSE_AFTER_ELLIPSIS = 1.3
PAUSE_AFTER_QUESTION_EXCLAIM = 0.75
PAUSE_AFTER_PERIOD = 0.45
DEFAULT_PAUSE = 0.5

ARABIC_DIACRITICS_PATTERN = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u08D3-\u08E1\u08E3-\u08FF]")
_WORD_TOKEN_PATTERN = re.compile(r"[\w\u0600-\u06FF]+", re.UNICODE)
HARD_WORDS_DIACRITICS = {
    "عدة": "عِدّة", "قلبه": "قَلْبه", "لعنة": "لَعنة", "مسكون": "مَسكون",
    "جثة": "جُثّة", "همس": "هَمْس", "أشباح": "أَشباح", "ظل": "ظِلّ",
    "رعب": "رُعب", "صرخة": "صَرخة",
}


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit("❌ فشل الأمر:\n" + " ".join(command) + "\n\n" + result.stderr)
    return result


def strip_diacritics(text: str) -> str:
    return ARABIC_DIACRITICS_PATTERN.sub("", text)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", strip_diacritics(text)).strip()


def apply_light_diacritics(text: str) -> str:
    def replace(match: re.Match) -> str:
        word = match.group(0)
        return HARD_WORDS_DIACRITICS.get(word, word)
    return _WORD_TOKEN_PATTERN.sub(replace, text)


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!؟…])\s+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def pause_duration_for(sentence: str) -> float:
    stripped = sentence.strip()
    if stripped.endswith("…") or stripped.endswith("..."):
        return PAUSE_AFTER_ELLIPSIS
    if stripped.endswith("؟") or stripped.endswith("!"):
        return PAUSE_AFTER_QUESTION_EXCLAIM
    if stripped.endswith("."):
        return PAUSE_AFTER_PERIOD
    return DEFAULT_PAUSE


def probe_duration(path: Path) -> float:
    result = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    return float(result.stdout.strip())


def build_silence_clip(duration: float, path: Path) -> None:
    run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
        "-t", f"{duration:.3f}", "-c:a", "libmp3lame", "-b:a", "192k", str(path),
    ])


async def synthesize_sentences(sentences: list[str]) -> list[dict]:
    segments = []
    for index, sentence in enumerate(sentences):
        seg_path = CLIPS_DIR / f"_seg_full_{index:03d}.mp3"
        events = []
        communicate = edge_tts.Communicate(sentence, VOICE, rate=RATE, pitch=PITCH, volume=VOLUME)
        with seg_path.open("wb") as audio_file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    events.append(chunk)
        duration = probe_duration(seg_path)
        segments.append({"path": seg_path, "duration": duration, "events": events, "sentence": sentence, "is_silence": False})
        if index < len(sentences) - 1:
            pause = pause_duration_for(sentence)
            pause_path = CLIPS_DIR / f"_pause_full_{index:03d}.mp3"
            build_silence_clip(pause, pause_path)
            segments.append({"path": pause_path, "duration": pause, "events": None, "sentence": None, "is_silence": True})
    return segments


def ass_time(seconds: float) -> str:
    centiseconds = max(0, int(round(seconds * 100)))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def two_lines(words: list[str]) -> str:
    words = [word.strip() for word in words if word.strip()]
    if len(words) <= 2:
        return "\u200f" + " ".join(words)
    midpoint = (len(words) + 1) // 2
    return "\u200f" + " ".join(words[:midpoint]) + r"\N\u200f" + " ".join(words[midpoint:])


def build_ass_header() -> str:
    style = "Style: Caption,Arial,58,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,3,0,2,70,70,90,1"
    return (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {VIDEO_W}\nPlayResY: {VIDEO_H}\n"
        "WrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
        "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        + style + "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def synthesize_voice(voice_text: str) -> None:
    sentences = split_sentences(voice_text)
    if not sentences:
        sys.exit("❌ النص فارغ ولا يمكن إنشاء صوت.")
    segments = asyncio.run(synthesize_sentences(sentences))
    inputs: list[str] = []
    for segment in segments:
        inputs += ["-i", str(segment["path"])]
    concat_filter = "".join(f"[{i}:a]" for i in range(len(segments))) + f"concat=n={len(segments)}:v=0:a=1[aout]"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", concat_filter, "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", str(VOICE_AUDIO)])

    all_word_events = []
    cumulative_seconds = 0.0
    for segment in segments:
        if segment["is_silence"]:
            cumulative_seconds += segment["duration"]
            continue
        if segment["events"]:
            for event in segment["events"]:
                all_word_events.append({
                    "offset": event["offset"] + int(cumulative_seconds * 10_000_000),
                    "duration": event["duration"],
                    "text": strip_diacritics(event["text"]),
                })
        else:
            words = re.findall(r"\S+", segment["sentence"] or "")
            per_word = segment["duration"] / max(len(words), 1)
            for word_index, word in enumerate(words):
                all_word_events.append({
                    "offset": int((cumulative_seconds + word_index * per_word) * 10_000_000),
                    "duration": int(per_word * 10_000_000),
                    "text": strip_diacritics(word),
                })
        cumulative_seconds += segment["duration"]

    if not all_word_events:
        sys.exit("❌ تعذر إنشاء توقيت الترجمة.")
    dialogue_lines = []
    for index in range(0, len(all_word_events), WORDS_PER_CAPTION_CHUNK):
        group = all_word_events[index:index + WORDS_PER_CAPTION_CHUNK]
        start = group[0]["offset"] / 10_000_000
        end = (group[-1]["offset"] + group[-1]["duration"]) / 10_000_000
        dialogue_lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(max(end, start + 0.25))},Caption,,0,0,0,,{two_lines([e['text'] for e in group])}")
    SUBTITLES.write_text(build_ass_header() + "\n".join(dialogue_lines) + "\n", encoding="utf-8")
    for segment in segments:
        Path(segment["path"]).unlink(missing_ok=True)


def mix_music_into_voice() -> None:
    if not BACKGROUND_MUSIC.exists():
        run(["ffmpeg", "-y", "-i", str(VOICE_AUDIO), "-c:a", "libmp3lame", "-b:a", "192k", str(FINAL_AUDIO)])
        return
    run([
        "ffmpeg", "-y", "-i", str(VOICE_AUDIO), "-stream_loop", "-1", "-i", str(BACKGROUND_MUSIC),
        "-filter_complex", f"[0:a]volume=1.0[voice];[1:a]volume={MUSIC_VOLUME}[music];[voice][music]amix=inputs=2:duration=first:dropout_transition=3:normalize=0[aout]",
        "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", "-shortest", str(FINAL_AUDIO),
    ])


def main() -> None:
    if not EPISODE_PATH.exists():
        sys.exit("❌ state/current_episode.json غير موجود.")
    episode = json.loads(EPISODE_PATH.read_text(encoding="utf-8"))
    narration = normalize_text(str(episode.get("narration", "")))
    if not narration:
        sys.exit("❌ حقل narration غير موجود أو فارغ.")

    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    synthesize_voice(apply_light_diacritics(narration))
    mix_music_into_voice()

    episode.pop("parts", None)
    episode["narration"] = narration
    episode["voice_audio"] = str(VOICE_AUDIO)
    episode["final_audio"] = str(FINAL_AUDIO)
    episode["subtitles"] = str(SUBTITLES)
    EPISODE_PATH.write_text(json.dumps(episode, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ صوت كامل: {FINAL_AUDIO}")
    print(f"✅ ترجمة أفقية متزامنة: {SUBTITLES}")


if __name__ == "__main__":
    main()
