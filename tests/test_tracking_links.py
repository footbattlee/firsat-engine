import base64
from uuid import UUID
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from tracking_links import tracked_deal_url


def test_tracking_link_contains_only_ids_and_channel():
    data = {
        "id": "11111111-1111-4111-8111-111111111111",
        "offer_id": "22222222-2222-4222-8222-222222222222",
        "product_url": "https://merchant.example/secret-path",
        "affiliate_url": "https://affiliate.example/tag",
    }
    url = tracked_deal_url(data, "telegram")
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    assert parsed.hostname == "fırsatcı.com"
    code = parsed.path.removeprefix("/f/")
    decoded = base64.urlsafe_b64decode(code + "=")
    assert decoded == UUID(data["id"]).bytes + UUID(data["offer_id"]).bytes
    assert query == {"s": ["telegram"]}
    assert "merchant.example" not in url
    assert "affiliate.example" not in url


def test_unknown_channel_becomes_other():
    data = {"id": "11111111-1111-4111-8111-111111111111", "offer_id": "22222222-2222-4222-8222-222222222222"}
    assert parse_qs(urlsplit(tracked_deal_url(data, "unknown")).query)["s"] == ["other"]


def test_cloud_click_tracking_deduplicates_visitors_and_detects_preview_headers():
    source = Path("supabase/functions/deal-click/index.ts").read_text(encoding="utf-8")
    assert "visitor_hash" in source
    classifier = Path("supabase/functions/_shared/click-request.mjs").read_text(encoding="utf-8")
    assert '"sec-purpose"' in classifier


def test_cloud_publish_restores_story_helper_message():
    source = Path("supabase/functions/telegram-approval-webhook/index.ts").read_text(encoding="utf-8")
    assert '"telegram","instagram","facebook","story"' in source
    assert "publishStory" in source
    assert "STORY_CHAT_ID" in source


def test_story_link_keeps_its_own_channel():
    data = {"id": "11111111-1111-4111-8111-111111111111", "offer_id": "22222222-2222-4222-8222-222222222222"}
    query = parse_qs(urlsplit(tracked_deal_url(data, "story")).query)
    assert query["s"] == ["story"]


def test_story_helper_contains_tracked_product_link():
    source = Path("supabase/functions/telegram-approval-webhook/index.ts").read_text(encoding="utf-8")
    assert 'tracked(d,"story")' in source


def test_cloud_click_tracking_keeps_story_channel():
    source = Path("supabase/functions/deal-click/index.ts").read_text(encoding="utf-8")
    assert '"story"' in source


def test_click_report_uses_short_preview_window():
    migration = Path(
        "supabase/migrations/20261004114500_refine_click_report_preview_window.sql"
    ).read_text(encoding="utf-8")
    assert "interval '15 seconds'" in migration
