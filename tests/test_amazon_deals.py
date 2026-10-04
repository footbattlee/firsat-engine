from collectors.amazon_deals import merge_products, parse_deal_page


HTML = """
<html><body>
  <div class="a-cardui dcl-product">
    <a class="a-link-normal dcl-product-link" href="/Sample/dp/B0ABCDE123?ref=x">
      <img src="https://img.example/one.jpg" alt="Örnek Kahve Makinesi" />
      <span class="dcl-product-title">Örnek Kahve Makinesi</span>
      <span class="a-price"><span class="a-offscreen">1.499,90 TL</span></span>
      <span class="a-text-price"><span class="a-offscreen">1.999,00 TL</span></span>
    </a>
  </div>
  <div class="a-cardui dcl-product">
    <a class="a-link-normal dcl-product-link" href="/Other/dp/B0FGHIJ456">
      <img src="https://img.example/two.jpg" alt="Kablosuz Kulaklık" />
      <span class="a-price"><span class="a-offscreen">799,00 TL</span></span>
      <span class="a-text-price"><span class="a-offscreen">699,00 TL</span></span>
    </a>
  </div>
</body></html>
"""


def test_parse_deal_cards_uses_real_prices_and_canonical_links():
    rows = parse_deal_page(HTML, "Fırsatlar")
    assert len(rows) == 2
    assert rows[0]["asin"] == "B0ABCDE123"
    assert rows[0]["price"] == 1499.90
    assert rows[0]["old_price"] == 1999.00
    assert rows[0]["product_url"] == "https://www.amazon.com.tr/dp/B0ABCDE123"
    assert "tag=" in rows[0]["affiliate_url"]
    assert rows[1]["old_price"] is None


def test_merge_products_deduplicates_carousel_and_grid_by_asin():
    first = parse_deal_page(HTML, "Fırsatlar")
    duplicate = dict(
        first[0],
        price=1399.90,
        old_price=None,
        deal_source="Fiyatları Dondurduk",
    )
    rows = merge_products([first, [duplicate]])
    assert len(rows) == 2
    assert rows[0]["price"] == 1399.90
    assert rows[0]["deal_source"] == "Fırsatlar + Fiyatları Dondurduk"


def test_parse_page_keeps_lower_duplicate_price_after_unique_limit():
    duplicate_html = HTML.replace("1.499,90 TL", "1.399,90 TL")
    rows = parse_deal_page(HTML + duplicate_html, "Fırsatlar", limit=1)
    assert len(rows) == 1
    assert rows[0]["price"] == 1399.90


def test_merge_keeps_lower_price_in_both_orders_without_mutating_inputs():
    first = parse_deal_page(HTML, "Fırsatlar")[0]
    lower = dict(first, price=1399.90, old_price=None, deal_source="Çok Al Az Öde")
    for groups in ([[first], [lower]], [[lower], [first]]):
        rows = merge_products(groups)
        assert len(rows) == 1
        assert rows[0]["price"] == 1399.90
        assert rows[0]["old_price"] is None
        assert set(rows[0]["deal_source"].split(" + ")) == {"Fırsatlar", "Çok Al Az Öde"}
    assert first["deal_source"] == "Fırsatlar"
    assert lower["deal_source"] == "Çok Al Az Öde"