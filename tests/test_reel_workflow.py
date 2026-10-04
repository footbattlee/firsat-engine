from pathlib import Path

import imageio_ffmpeg
from PIL import Image

from creative.generate_deal_reel import _voiceover_text, render_reel
from run_telegram_approval import keyboard


def test_approval_keyboard_has_separate_reel_action():
    buttons = keyboard("candidate-1")["inline_keyboard"]
    actions = [button["callback_data"] for row in buttons for button in row]
    assert "publish:candidate-1" not in actions
    assert "reel:candidate-1" in actions
    assert actions.count("reel:candidate-1") == 1
    assert "reject:candidate-1" in actions


def test_render_reel_produces_vertical_h264_mp4(tmp_path):
    story = tmp_path / "story.png"
    Image.new("RGB", (1080, 1920), (248, 249, 247)).save(story)
    data = {
        "id": "test-candidate",
        "title": "Test Ürünü",
        "gap_percent": 25,
        "cheapest_price": 799,
    }
    output = render_reel(data, story, tmp_path / "test-reel.mp4")
    assert Path(output).exists()
    assert Path(output).stat().st_size > 10_000

    frames, seconds = imageio_ffmpeg.count_frames_and_secs(str(output))
    assert 290 <= frames <= 305
    assert 9.5 <= seconds <= 10.5


def test_voiceover_starts_with_product_price_and_discount():
    text = _voiceover_text({
        "title": "Stanley Aerolight Termos",
        "cheapest_price": 900,
        "gap_percent": 62.79,
    })
    assert "Stanley Aerolight Termos" in text
    assert "Şimdi 900 TL" in text
    assert "yüzde 63 daha ucuz" in text
    assert "Anlık İndirim Radarı" in text


def test_cloud_reel_sends_video_and_copyable_caption_to_story_chat():
    source = Path("supabase/functions/telegram-approval-webhook/index.ts").read_text(encoding="utf-8")
    assert "async function sendReelAssist" in source
    assert 'TG_API+"/sendVideo"' in source
    assert "REELS AÇIKLAMASI — KOPYALA VE YAPIŞTIR" in source
    assert "try{await sendReelAssist(d)}catch" in source
