from collectors import trendyol


def test_price_parser_supports_current_trendyol_format():
    assert trendyol.parse_first_price("58,900 TL") == 58900
    assert trendyol.parse_first_price("1,163.03 TL") == 1163.03


def test_price_parser_supports_turkish_format():
    assert trendyol.parse_first_price("58.900 TL") == 58900
    assert trendyol.parse_first_price("1.163,03 TL") == 1163.03
    assert trendyol.parse_first_price("300,00 TL") == 300


def test_price_parser_rejects_promotional_line_in_fallback():
    text = "30 TL Kupon\nKargo Bedava\n58,900 TL"
    assert trendyol.fallback_price_from_text(text) == 58900


def test_existing_offer_price_collapse_is_suspicious():
    assert trendyol.suspicious_price_drop(57049, 9)
    assert not trendyol.suspicious_price_drop(57049, 50000)
