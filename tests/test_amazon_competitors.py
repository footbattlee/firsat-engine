import json
from types import SimpleNamespace
from unittest.mock import patch
from collectors import amazon_competitors as discovery
from collectors import amazon_deals
import run_pipeline

def seed(title="ACME Classic Tişört Siyah M"):
    return {"asin": "B0ABCDE123", "title": title, "brand": "ACME", "price": 200,
            "product_url": "https://www.amazon.com.tr/dp/B0ABCDE123"}

def item(title="ACME Classic Tişört Siyah M", price=250):
    return {"title": title, "brand": "ACME", "price": price, "in_stock": True}

def test_category_independent_query_keeps_apparel_variant():
    assert discovery.search_query(seed()) == "ACME Classic Tişört Siyah M"

def test_apparel_identity_rejects_size_color_and_missing_variants():
    with patch.object(discovery.matcher, "pair_score", return_value=(99, "exact")):
        assert discovery.same_product(seed(), item(), "n11")
        for title in ["ACME Classic Tişört Siyah L", "ACME Classic Tişört Beyaz M",
                      "ACME Classic Tişört", "ACME Classic Tişört Siyah"]:
            assert not discovery.same_product(seed(), item(title), "n11")

def test_invalid_price_or_stock_never_matches():
    with patch.object(discovery.matcher, "pair_score", return_value=(99, "exact")):
        for price in [0, -1, float("nan"), float("inf"), None]:
            assert not discovery.same_product(seed(), item(price=price), "n11")
        assert not discovery.same_product(seed(), dict(item(), in_stock=False), "n11")

def test_all_seed_products_search_all_stores_even_without_database_matches():
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        row = json.loads(kwargs["input"])
        slug = command[command.index("--store") + 1]
        result = {"asin": row["asin"], "store": slug, "status": "unverified"}
        return SimpleNamespace(returncode=0, stdout="AMAZON COMPETITOR RESULT | " + json.dumps(result))
    with patch.object(discovery.subprocess, "run", side_effect=run):
        results = discovery.discover_competitors([seed()], apply=False)
    assert len(results) == len(discovery.STORES)
    assert all("--apply" not in command for command, _ in calls)
    assert {r["store"] for r in results} == set(discovery.STORES)

def test_failed_store_does_not_cancel_other_searches():
    import subprocess
    with patch.object(discovery.subprocess, "run", side_effect=subprocess.TimeoutExpired("test", 1)):
        results = discovery.discover_competitors([seed()], timeout=1)
    assert len(results) == len(discovery.STORES)
    assert all(r["reason"] == "timeout" for r in results)

def test_pipeline_special_collector_enables_discovery():
    with patch.object(run_pipeline, "run_process", return_value={}) as run:
        run_pipeline.run_special_collector("Amazon", run_pipeline.AMAZON_DEALS_COLLECTOR)
    assert "--find-competitors" in run.call_args.args[2]

def test_sync_search_captures_results_without_category_filter():
    product = item()
    module = SimpleNamespace(collect=lambda **kwargs: [product])
    assert discovery.collect_candidates(module, seed(), 5) == [product]

def test_dry_run_never_persists_seed_or_competitor_prices(tmp_path):
    with patch("sys.argv", ["amazon_deals", "--dry-run", "--find-competitors"]), \
         patch.object(amazon_deals, "ROOT", tmp_path), \
         patch.object(amazon_deals, "collect", return_value=[seed()]), \
         patch.object(amazon_deals.amazon, "enrich_product", side_effect=lambda row, _: row), \
         patch.object(amazon_deals.amazon, "save_products_to_supabase") as save, \
         patch.object(amazon_deals.amazon, "supabase_request") as request, \
         patch.object(discovery, "discover_competitors", return_value=[]) as search:
        amazon_deals.main()
    save.assert_not_called()
    request.assert_not_called()
    assert search.call_args.kwargs["apply"] is False


def test_live_verified_price_is_saved_and_unrelated_results_are_ignored():
    from deals import refresh_competitor_offers as refresh
    from unittest.mock import Mock
    good = dict(item(), merchant_product_id="123", product_url="https://www.n11.com/urun/x-123")
    wrong = dict(item("ACME Classic Tişört Siyah L"), merchant_product_id="456")
    save = Mock(return_value=1)
    module = SimpleNamespace(collect=lambda **kwargs: [good, wrong], save_products_to_supabase=save)
    with patch.object(discovery.shared, "load_module", return_value=module), \
         patch.object(discovery.shared, "get_proxy_settings", return_value=None), \
         patch.object(discovery.shared, "enable_requests_proxy"), \
         patch.object(refresh, "fetch_verified", return_value={"price": 275, "currency": "TRY", "in_stock": True}) as verify:
        result = discovery.search_store(seed(), "n11", apply=True)
    assert result["saved"] == 1
    assert result["matched"] == 1
    assert verify.call_count == 1
    assert save.call_args.args[0][0]["price"] == 275

def test_failed_live_verification_never_saves_a_search_price():
    from deals import refresh_competitor_offers as refresh
    from unittest.mock import Mock
    product = dict(item(), merchant_product_id="123", product_url="https://www.n11.com/urun/x-123")
    save = Mock()
    module = SimpleNamespace(collect=lambda **kwargs: [product], save_products_to_supabase=save)
    with patch.object(discovery.shared, "load_module", return_value=module), \
         patch.object(discovery.shared, "get_proxy_settings", return_value=None), \
         patch.object(discovery.shared, "enable_requests_proxy"), \
         patch.object(refresh, "fetch_verified", side_effect=ValueError("unverified")):
        result = discovery.search_store(seed(), "n11", apply=True)
    save.assert_not_called()
    assert result["status"] == "unverified"

def test_global_matcher_keeps_apparel_variants_separate():
    a = dict(seed(), merchant_id="amazon")
    b = dict(item("ACME Classic Tişört Siyah L"), merchant_id="n11")
    score, reason = discovery.matcher.pair_score(a, b)
    assert score == 0
    assert reason == "apparel-variant-conflict"

def test_async_collector_is_captured_before_any_persistence():
    from unittest.mock import Mock
    original_save = Mock()
    module = SimpleNamespace(save_products_to_supabase=original_save)
    async def main():
        module.save_products_to_supabase([item()])
    module.main = main
    assert discovery.collect_candidates(module, seed(), 5) == [item()]
    original_save.assert_not_called()


def test_parallel_discovery_is_capped_and_serial_per_store():
    import threading
    import time
    lock = threading.Lock()
    active = set()
    maximum = 0
    def job(row, slug, apply, timeout, limit):
        nonlocal maximum
        with lock:
            assert slug not in active
            active.add(slug)
            maximum = max(maximum, len(active))
        time.sleep(0.01)
        with lock:
            active.remove(slug)
        return {"store": slug}
    with patch.object(discovery, "_search_job", side_effect=job), patch.dict("os.environ", {"DEAL_COMPETITOR_WORKERS": "9"}):
        rows = discovery.discover_competitors([seed(), seed(), seed()])
    assert 1 < maximum <= 3
    assert len(rows) == 15
