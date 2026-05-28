import json
import os
import subprocess

_CHARS_PER_SEC_ZH = 3.5
_WORDS_PER_SEC_EN = 2.5
_PAUSE = 0.8       # seconds between segments
_INTRO_DUR = 5.0
_OUTRO_DUR = 10.0
_SEG_BUFFER = 3.0  # visual dwell time added to each segment

_LANG_LABELS = {
    "zh": "每日科技速递",
    "en": "Daily Tech Digest",
}
_CTA_TEXTS = {
    "zh": "关注我们，订阅更多科技速递",
    "en": "Follow us for daily tech updates",
}
_OUTRO_LABELS = {
    "zh": "微信公众号 · DailyTechFlow",
    "en": "@DailyTechFlow",
}


def _estimate_seg_dur(narration: str, lang: str) -> float:
    if lang == "zh":
        return len(narration) / _CHARS_PER_SEC_ZH + _SEG_BUFFER
    words = len(narration.split())
    return words / _WORDS_PER_SEC_EN + _SEG_BUFFER


def _compute_timing(narrations: list[str], lang: str) -> dict:
    seg_durs = [_estimate_seg_dur(n, lang) for n in narrations]
    seg_starts = []
    t = _INTRO_DUR
    for i, dur in enumerate(seg_durs):
        seg_starts.append(round(t, 2))
        t += dur + (_PAUSE if i < len(seg_durs) - 1 else 0)
    audio_dur = sum(seg_durs) + _PAUSE * (len(seg_durs) - 1)
    outro_start = round(_INTRO_DUR + audio_dur, 2)
    return {
        "seg_starts": [round(s, 2) for s in seg_starts],
        "seg_durs": [round(d, 2) for d in seg_durs],
        "outro_start": outro_start,
        "total_dur": round(outro_start + _OUTRO_DUR, 2),
        "audio_dur": round(audio_dur, 2),
    }


def _fill_template(template: str, segments: list[dict], cover_path: str,
                   voiceover_path: str, lang: str, date_str: str, timing: dict) -> str:
    replacements = {
        "{{TOTAL_DURATION}}": str(timing["total_dur"]),
        "{{AUDIO_DURATION}}": str(timing["audio_dur"]),
        "{{VOICEOVER_PATH}}": voiceover_path,
        "{{LANG}}": lang,
        "{{LANG_LABEL}}": _LANG_LABELS[lang],
        "{{DATE_STR}}": date_str,
        "{{COVER_IMAGE_PATH}}": cover_path,
        "{{HEADLINE_1}}": segments[0]["headline"],
        "{{HEADLINE_2}}": segments[1]["headline"],
        "{{HEADLINE_3}}": segments[2]["headline"],
        "{{NARRATION_1}}": segments[0]["narration"],
        "{{NARRATION_2}}": segments[1]["narration"],
        "{{NARRATION_3}}": segments[2]["narration"],
        "{{SEG1_START}}": str(timing["seg_starts"][0]),
        "{{SEG2_START}}": str(timing["seg_starts"][1]),
        "{{SEG3_START}}": str(timing["seg_starts"][2]),
        "{{OUTRO_START}}": str(timing["outro_start"]),
        "{{CTA_TEXT}}": _CTA_TEXTS[lang],
        "{{OUTRO_LABEL}}": _OUTRO_LABELS[lang],
    }
    html = template
    for k, v in replacements.items():
        html = html.replace(k, v)
    return html


def _render_video(project_dir: str, html_filename: str, mp4_path: str) -> None:
    result = subprocess.run(
        ["hyperframes", "render", project_dir,
         "--composition", html_filename,
         "--output", mp4_path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"hyperframes render failed:\n{result.stderr}")
    if not os.path.exists(mp4_path) or os.path.getsize(mp4_path) == 0:
        raise RuntimeError(f"Output file missing or empty: {mp4_path}")


def run(date_str: str, config: dict) -> bool:
    output_dir = os.path.join(config["output_base"], date_str)
    template_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "templates", "hyperframes_template.html",
    )

    for fname in ["script_zh.json", "script_en.json",
                  "cover_zh.png", "cover_en.png",
                  "voiceover_zh.mp3", "voiceover_en.mp3"]:
        p = os.path.join(output_dir, fname)
        if not os.path.exists(p):
            raise FileNotFoundError(f"Missing: {p}")

    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Missing template: {template_path}")

    with open(template_path, encoding="utf-8") as f:
        template = f.read()

    try:
        for lang in ["zh", "en"]:
            script_path = os.path.join(output_dir, f"script_{lang}.json")
            with open(script_path, encoding="utf-8") as f:
                segments = json.load(f)

            timing = _compute_timing([s["narration"] for s in segments], lang)

            html = _fill_template(
                template, segments,
                cover_path=f"cover_{lang}.png",
                voiceover_path=f"voiceover_{lang}.mp3",
                lang=lang,
                date_str=date_str,
                timing=timing,
            )

            html_name = f"video_{lang}.html"
            with open(os.path.join(output_dir, html_name), "w", encoding="utf-8") as f:
                f.write(html)

            mp4_path = os.path.join(output_dir, f"video_{lang}.mp4")
            print(f"[video_synthesizer] Rendering {lang} video...")
            _render_video(output_dir, html_name, mp4_path)
            print(f"[video_synthesizer] video_{lang}.mp4 saved")

    except Exception as e:
        print(f"[video_synthesizer] Error: {e}")
        return False

    return True
