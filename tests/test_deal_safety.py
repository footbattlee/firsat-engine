from unittest.mock import Mock

from creative import generate_deal_creative as creative
from deals import deal_engine


def test_deal_engine_blocks_extreme_store_gap():
    assert deal_engine.suspicious_price_reason(99.98, {"history_drop_percent": 0})


def test_deal_engine_blocks_extreme_history_drop():
    assert deal_engine.suspicious_price_reason(40, {"history_drop_percent": 80})


def test_deal_engine_allows_plausible_discount():
    assert deal_engine.suspicious_price_reason(25, {"history_drop_percent": 10}) is None


def candidate(**changes):
    row = {
        "title": "Apple iPhone 15 128 GB",
        "brand": "Apple",
        "cheapest_price": 50000,
        "competitor_price": 60000,
        "gap_percent": 16.67,
        "history_drop_percent": 5,
        "merchant": "Example",
        "product_url": "https://example.com/product",
        "image_url": "https://example.com/image.jpg",
    }
    row.update(changes)
    return row


def test_creative_gate_blocks_extreme_gap(monkeypatch):
    image = Mock()
    monkeypatch.setattr(creative, "download_image", Mock(return_value=image))
    result = creative.validate_candidate(
        candidate(cheapest_price=9, competitor_price=59424.89, gap_percent=99.98)
    )
    assert not result["ok"]
    assert any(x.startswith("SUSPICIOUS_PRICE_GAP") for x in result["errors"])


def test_creative_gate_blocks_extreme_history_drop(monkeypatch):
    image = Mock()
    monkeypatch.setattr(creative, "download_image", Mock(return_value=image))
    result = creative.validate_candidate(candidate(history_drop_percent=75))
    assert not result["ok"]
    assert any(x.startswith("SUSPICIOUS_HISTORY_DROP") for x in result["errors"])


def test_sent_price_reconstructed_from_dispatch_time():
    from datetime import datetime, timezone
    offers = [{"id": "a"}, {"id": "b"}]
    history = {
        "a": [
            {"price": 15999, "checked_at": datetime(2026, 10, 2, tzinfo=timezone.utc)},
            {"price": 23999, "checked_at": datetime(2026, 10, 1, 18, 20, tzinfo=timezone.utc)},
        ],
        "b": [
            {"price": 17670, "checked_at": datetime(2026, 10, 2, tzinfo=timezone.utc)},
            {"price": 17549, "checked_at": datetime(2026, 10, 1, 18, 19, tzinfo=timezone.utc)},
        ],
    }
    sent_at = "2026-10-01T18:52:25+00:00"
    assert deal_engine.sent_price_at(offers, history, sent_at) == 17549


def test_redispatch_uses_last_sent_price():
    drop = deal_engine.redispatch_drop_percent(15999, 17549)
    assert round(drop, 2) == 8.83
    assert drop < deal_engine.REDISPATCH_PRICE_DROP_PERCENT


def test_creative_gate_blocks_low_gap_without_redispatch(monkeypatch):
    image = Mock()
    monkeypatch.setattr(creative, "download_image", Mock(return_value=image))
    result = creative.validate_candidate(
        candidate(cheapest_price=9997, competitor_price=10000, gap_percent=0.03)
    )
    assert not result["ok"]
    assert any(x.startswith("DEAL_GAP_BELOW_THRESHOLD") for x in result["errors"])


def test_creative_gate_allows_low_gap_after_meaningful_telegram_price_drop(monkeypatch):
    image = Mock()
    monkeypatch.setattr(creative, "download_image", Mock(return_value=image))
    result = creative.validate_candidate(
        candidate(
            cheapest_price=9997,
            competitor_price=10000,
            gap_percent=0.03,
            notification_reason="redispatch_price_drop",
            redispatch_drop_percent=24,
            previous_notified_price=13154,
        )
    )
    assert result["ok"]
    assert creative.display_discount({
        "notification_reason": "redispatch_price_drop",
        "redispatch_drop_percent": 24,
        "gap_percent": 0.03,
    }) == (24.0, "SON PAYLAŞIMA GÖRE")


def test_creative_gate_blocks_fake_redispatch_below_five_percent(monkeypatch):
    image = Mock()
    monkeypatch.setattr(creative, "download_image", Mock(return_value=image))
    result = creative.validate_candidate(
        candidate(
            cheapest_price=9997,
            competitor_price=10000,
            gap_percent=0.03,
            notification_reason="redispatch_price_drop",
            redispatch_drop_percent=0.03,
            previous_notified_price=10000,
        )
    )
    assert not result["ok"]
    assert any(x.startswith("REDISPATCH_DROP_BELOW_THRESHOLD") for x in result["errors"])


def test_redispatch_caption_shows_telegram_drop_not_tiny_store_gap():
    import run_telegram_approval as approval

    data = candidate(
        notification_reason="redispatch_price_drop",
        redispatch_drop_percent=24,
        previous_notified_price=13154,
        cheapest_price=9997,
        competitor_price=10000,
        gap_percent=0.03,
    )
    text = approval.caption(data, {"warnings": []})
    assert "Son paylaşımdan sonra %24,00 düştü" in text
    assert "Rakip mağaza farkı: %0,03" in text
    assert "%0,03 daha ucuz" not in text

def test_saved_notification_price_wins_over_history_reconstruction():
    assert deal_engine.last_notification_price(
        {"notified_price": 1000, "sent_at": "2026-10-04T12:00:00Z"}, [], {}
    ) == 1000


def test_repeat_metadata_takes_priority_over_qualifying_competitor_gap():
    data = deal_engine.redispatch_metadata(True, 2699, 18.52538)
    assert data["notification_reason"] == "redispatch_price_drop"
    assert data["previous_notified_price"] == 2699
    assert data["redispatch_drop_percent"] == 18.53


def test_repeat_threshold_is_at_least_fifteen_percent():
    assert deal_engine.REDISPATCH_PRICE_DROP_PERCENT >= 15


def test_sub_fifteen_repeat_is_blocked_even_with_large_store_gap(monkeypatch):
    monkeypatch.setenv("REDISPATCH_PRICE_DROP_PERCENT", "5")
    monkeypatch.setattr(creative, "download_image", Mock(return_value=Mock()))
    result = creative.validate_candidate(candidate(
        cheapest_price=851, competitor_price=1200, gap_percent=29.08,
        notification_reason="redispatch_price_drop", redispatch_drop_percent=14.9,
        previous_notified_price=1000,
    ))
    assert not result["ok"]
    assert any(x.startswith("REDISPATCH_DROP_BELOW_THRESHOLD") for x in result["errors"])


def test_fifteen_repeat_uses_previous_price_and_not_competitor_caption(monkeypatch):
    import run_telegram_approval as approval
    monkeypatch.setattr(creative, "download_image", Mock(return_value=Mock()))
    data = candidate(cheapest_price=850, competitor_price=1200, gap_percent=29.17,
        **deal_engine.redispatch_metadata(True, 1000, 15))
    assert creative.validate_candidate(data)["ok"]
    text = approval.caption(data, {"warnings": []})
    assert "%15,00" in text
    assert "%29,17" in text
    assert approval.comparison_price(data)[1] == 1000


def test_inflated_repeat_discount_cannot_pass_gate(monkeypatch):
    monkeypatch.setattr(creative, "download_image", Mock(return_value=Mock()))
    result = creative.validate_candidate(candidate(
        cheapest_price=950,competitor_price=1200,gap_percent=20.83,
        notification_reason="redispatch_price_drop",redispatch_drop_percent=25,
        previous_notified_price=1000))
    assert not result["ok"]
    assert "REDISPATCH_DROP_MISMATCH" in result["errors"]
