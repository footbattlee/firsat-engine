import json
from unittest.mock import patch
import pytest
from collectors import marketplace_deals as deals, amazon_competitors as search
import run_pipeline


def html(condition='NewCondition', stock='InStock', price=100):
    return '<script type="application/ld+json">'+json.dumps({'@type':'Product','name':'ACME Model X','brand':{'name':'ACME'},'offers':{'@type':'Offer','price':price,'priceCurrency':'TRY','availability':'https://schema.org/'+stock,'itemCondition':'https://schema.org/'+condition}})+'</script>'


def test_listing_only_accepts_store_product_links_and_deduplicates():
    page = '<a href="/acme/model-p-123?x=1">x</a><a href="/acme/model-p-123?x=2">x</a><a href="https://evil.example/model-p-4">x</a><a href="/kampanyalar">x</a>'
    assert deals.product_urls(page,'trendyol') == ['https://www.trendyol.com/acme/model-p-123']


@pytest.mark.parametrize('slug,url', [('trendyol','https://www.trendyol.com/acme/model-p-123'),('hepsiburada','https://www.hepsiburada.com/model-p-HBCV123')])
def test_source_and_price_are_verified(slug,url):
    row=deals.detail_product(html(),url,slug)
    assert row['source_store']==slug and row['price']==100 and row['in_stock']


@pytest.mark.parametrize('condition,stock,price',[('UsedCondition','InStock',100),('NewCondition','OutOfStock',100),('NewCondition','InStock',0),('NewCondition','InStock',float('nan'))])
def test_invalid_stock_condition_and_price_are_rejected(condition,stock,price):
    with pytest.raises(ValueError):
        deals.detail_product(html(condition,stock,price),'https://www.trendyol.com/acme/model-p-123','trendyol')


@pytest.mark.parametrize('source',['trendyol','hepsiburada','amazon'])
def test_searches_five_other_stores_including_amazon(source):
    stores=search.competitor_stores({'source_store':source})
    assert len(stores)==5 and source not in stores
    if source!='amazon':
        assert 'amazon' in stores


@pytest.mark.parametrize('slug',['trendyol','hepsiburada'])
def test_dry_run_cannot_persist_and_invokes_competitor_discovery(slug,tmp_path):
    row={'source_store':slug,'merchant_product_id':'123','title':'ACME Model X','price':100}
    module=deals.trendyol if slug=='trendyol' else deals.hb
    with patch('sys.argv',['deals','--dry-run','--find-competitors']), patch.object(deals,'ROOT',tmp_path), patch.object(deals,'collect',return_value=[row]), patch.object(module,'save_products_to_supabase') as save, patch.object(deals,'discover_competitors',return_value=[]) as find:
        deals.main(slug)
    save.assert_not_called()
    assert find.call_args.kwargs['apply'] is False


@pytest.mark.parametrize('slug',['trendyol','hepsiburada'])
def test_pipeline_enables_discovery_for_new_sources(slug):
    with patch.object(run_pipeline,'run_process',return_value={}) as run:
        run_pipeline.run_special_collector(slug,run_pipeline.ROOT/'collectors'/f'{slug}_deals.py')
    assert '--find-competitors' in run.call_args.args[2]