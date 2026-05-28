import asyncio
import json
import os

import edge_tts

_VOICE_ZH = "zh-CN-XiaoxiaoNeural"
_VOICE_EN = "en-US-JennyNeural"
_PAUSE_TAG = '<break time="800ms"/>'


def _load_narrations(script_path: str) -> list[str]:
    with open(script_path, encoding="utf-8") as f:
        segments = json.load(f)
    if not segments:
        raise ValueError(f"Empty script: {script_path}")
    return [seg["narration"] for seg in segments]


async def _synthesize(narrations: list[str], voice: str, out_path: str) -> None:
    text = _PAUSE_TAG.join(narrations)
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(out_path)


def run(date_str: str, config: dict) -> bool:
    output_dir = os.path.join(config["output_base"], date_str)

    script_zh = os.path.join(output_dir, "script_zh.json")
    script_en = os.path.join(output_dir, "script_en.json")

    if not os.path.exists(script_zh):
        raise FileNotFoundError(f"Missing: {script_zh}")
    if not os.path.exists(script_en):
        raise FileNotFoundError(f"Missing: {script_en}")

    try:
        narrations_zh = _load_narrations(script_zh)
        narrations_en = _load_narrations(script_en)

        out_zh = os.path.join(output_dir, "voiceover_zh.mp3")
        out_en = os.path.join(output_dir, "voiceover_en.mp3")

        print(f"[voice_generator] Generating zh voiceover ({len(narrations_zh)} segments)...")
        asyncio.run(_synthesize(narrations_zh, _VOICE_ZH, out_zh))
        print(f"[voice_generator] voiceover_zh.mp3 saved")

        print(f"[voice_generator] Generating en voiceover ({len(narrations_en)} segments)...")
        asyncio.run(_synthesize(narrations_en, _VOICE_EN, out_en))
        print(f"[voice_generator] voiceover_en.mp3 saved")

    except Exception as e:
        print(f"[voice_generator] Error: {e}")
        return False

    print(f"[voice_generator] Both voiceovers saved to {output_dir}")
    return True
