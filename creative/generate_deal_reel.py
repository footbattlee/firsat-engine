import os
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw

from creative.generate_deal_creative import BG, INK, NAVY_DARK, ORANGE, WHITE, font, money, wrap_lines

SIZE = (1080, 1920)
OUT_DIR = Path(os.getenv("CREATIVE_OUTPUT_DIR", "creative_output"))
VOICE_SCRIPT = Path(__file__).resolve().parent / "synthesize_reel_voice.ps1"


def _centered(draw, text, y, text_font, fill, *, max_width=960):
    lines = wrap_lines(draw, text, text_font, max_width, 3)
    line_height = int(text_font.size * 1.18)
    for index, line in enumerate(lines):
        box = draw.textbbox((0, 0), line, font=text_font)
        x = (SIZE[0] - (box[2] - box[0])) // 2
        draw.text((x, y + index * line_height), line, font=text_font, fill=fill)


def _outro_frame(data, path):
    image = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((95, 190, 985, 600), 80, fill=ORANGE)
    _centered(draw, "FIRSATI KAÇIRMA", 285, font(76, True), WHITE)
    _centered(draw, money(data["cheapest_price"]), 760, font(100, True), NAVY_DARK)
    _centered(draw, "Güncel fırsatlar için takip et", 1120, font(45, True), INK)
    _centered(draw, "@anlikindirimradari", 1250, font(61, True), ORANGE)
    _centered(draw, "Link biyografide ve Telegram kanalında", 1540, font(34, True), INK)
    image.save(path, "PNG")


def _voiceover_text(data):
    title = " ".join(str(data.get("title") or "Bu fırsat").split())
    if len(title) > 80:
        title = title[:77].rsplit(" ", 1)[0] + "..."
    if data.get("notification_reason") == "redispatch_price_drop":
        percent = float(data.get("redispatch_drop_percent") or 0)
        comparison = f"Son paylaşım fiyatına göre yüzde {percent:.0f} düştü."
    else:
        percent = float(data.get("gap_percent") or 0)
        comparison = f"Rakip mağazaya göre yüzde {percent:.0f} daha ucuz."
    return (
        f"{title}. Şimdi {money(data['cheapest_price'])}. "
        f"{comparison} Yeni fırsatlar için Anlık İndirim Radarı'nı takip et."
    )


def _synthesize_voiceover(data, output):
    enabled = os.getenv("REELS_VOICEOVER_ENABLED", "1").strip().lower()
    if os.name != "nt" or enabled in {"0", "false", "no"} or not VOICE_SCRIPT.exists():
        return None
    voice = os.getenv("REELS_VOICE_NAME", "Microsoft Tolga").strip() or "Microsoft Tolga"
    bundled_pwsh = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe"
    powershell = (
        shutil.which("pwsh.exe")
        or (str(bundled_pwsh) if bundled_pwsh.exists() else None)
        or shutil.which("powershell.exe")
    )
    if not powershell:
        return None
    completed = subprocess.run(
        [
            powershell, "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(VOICE_SCRIPT),
            "-Text", _voiceover_text(data),
            "-OutputPath", str(output),
            "-VoiceName", voice,
        ],
        capture_output=True,
        text=True,
        timeout=45,
    )
    if completed.returncode != 0 or not output.exists():
        print("REEL VOICE WARNING | " + (completed.stderr or completed.stdout)[-1000:])
        return None
    return output


def reel_output_path(data):
    return OUT_DIR / f"deal_{data['id']}_reel_1080x1920.mp4"


def render_reel(data, story_path, output_path=None):
    output = Path(output_path) if output_path else reel_output_path(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    work = output.parent / (output.stem + "_frames")
    work.mkdir(parents=True, exist_ok=True)
    outro = work / "outro.png"
    voiceover = work / "voiceover.wav"
    _outro_frame(data, outro)
    audio = _synthesize_voiceover(data, voiceover)

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    temp = output.with_suffix(".tmp.mp4")
    filter_graph = (
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,fps=30,format=yuv420p,setsar=1,"
        "zoompan=z='min(max(zoom,pzoom)+0.00018,1.035)':"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=30[v0];"
        "[1:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,fps=30,format=yuv420p,setsar=1[v1];"
        "[v0][v1]xfade=transition=fade:duration=0.35:offset=7.30[outv]"
    )
    command = [
        ffmpeg, "-y",
        "-loop", "1", "-t", "7.65", "-i", str(story_path),
        "-loop", "1", "-t", "2.4", "-i", str(outro),
    ]
    if audio:
        command += ["-i", str(audio)]
        filter_graph += ";[2:a]aresample=44100,apad=pad_dur=9.70,atrim=duration=9.70[aout]"
    command += [
        "-filter_complex", filter_graph,
        "-map", "[outv]", "-r", "30", "-c:v", "libx264",
        "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
    ]
    if audio:
        command += ["-map", "[aout]", "-c:a", "aac", "-b:a", "128k"]
    else:
        command += ["-an"]
    command += ["-t", "9.70", str(temp)]

    completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if completed.returncode != 0:
        raise RuntimeError("FFmpeg Reels üretimi başarısız: " + completed.stderr[-2000:])
    os.replace(temp, output)
    shutil.rmtree(work, ignore_errors=True)
    return output
