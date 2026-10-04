import json
from datetime import datetime, timezone
from unittest.mock import Mock
import pytest
from deals import refresh_competitor_offers as r

CUT = datetime(2026, 9, 29, tzinfo=timezone.utc)
OLD = '2026-09-28T12:00:00+00:00'
NEW = '2026-09-29T12:00:00+00:00'

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(r.requests.Session, 'get', Mock(side_effect=AssertionError('network forbidden')))
    monkeypatch.setattr(r.db, 'sb_patch', Mock(side_effect=AssertionError('database forbidden')))
    monkeypatch.setattr(r, 'append_price_history', Mock(side_effect=AssertionError('database forbidden')))

def offer(id, merchant, checked=OLD, **kw):
    return dict(id=id, product_variant_id='v', merchant_id=merchant,
                merchant_product_id='123', last_checked_at=checked,
                price=100, in_stock=True, product_url='https://www.n11.com/urun/example-123', **kw)

def targets(offers):
    return r.select_targets([{'id':'c'}], [{'canonical_product_id':'c','product_id':'p'}],
                            [{'id':'v','product_id':'p'}], offers, CUT)

def page(**changes):
    value={'@type':'Product','sku':'123','offers':{'@type':'Offer','price':'125.50',
               'priceCurrency':'TRY','availability':'https://schema.org/InStock'}}
    value.update(changes)
    return '<script type="application/ld+json">'+json.dumps(value)+'</script>'

def test_only_missing_competitors_selected():
    a=offer('a','one',NEW); b=offer('b','two'); c=offer('c','one')
    assert [x['id'] for x in targets([a,b,c])] == ['b']
    assert targets([b,c]) == []
    assert targets([a,offer('b','two',NEW)]) == []

def test_out_of_stock_competitor_is_rechecked():
    b=offer('b','two'); b['in_stock']=False
    assert [x['id'] for x in targets([offer('a','one',NEW),b])] == ['b']
    b['last_checked_at']=NEW
    assert targets([offer('a','one',NEW),b]) == []

def test_unmatched_variants_not_selected():
    b=offer('b','two'); b['product_variant_id']='unknown'
    assert targets([offer('a','one',NEW),b]) == []

def test_verified_price():
    assert r.parse_verified(page(),offer('b','two'),'n11') == {'price':125.5,'currency':'TRY','in_stock':True}

@pytest.mark.parametrize('change',[
 {'offers':{}},
 {'offers':{'@type':'AggregateOffer','lowPrice':1,'priceCurrency':'TRY','availability':'https://schema.org/InStock'}},
 {'offers':{'@type':'Offer','price':'NaN','priceCurrency':'TRY','availability':'https://schema.org/InStock'}},
 {'offers':{'@type':'Offer','price':1,'priceCurrency':'USD','availability':'https://schema.org/InStock'}},
 {'offers':{'@type':'Offer','price':1,'priceCurrency':'TRY'}},
])
def test_ambiguous_data_rejected(change):
    with pytest.raises(ValueError): r.parse_verified(page(**change),offer('b','two'),'n11')

def test_out_of_stock_verified():
    html=page().replace('InStock','OutOfStock')
    assert r.parse_verified(html,offer('b','two'),'n11')['in_stock'] is False

def test_duplicate_product_evidence_rejected():
    with pytest.raises(ValueError):r.parse_verified(page()+page(),offer('b','two'),'n11')

def test_recommendations_not_parsed():
    html='<script type="application/ld+json">'+json.dumps({'@type':'ItemList','itemListElement':[json.loads(page().split('>',1)[1].split('</')[0])]})+'</script>'
    with pytest.raises(ValueError):r.parse_verified(html,offer('b','two'),'n11')

def test_amazon_requires_identity_stock_and_live_price():
    html='<input id="ASIN" value="123"><span id="productTitle">Device</span><div id="availability">Stokta var</div><div id="corePrice_feature_div"><span class="a-price"><span class="a-offscreen">1.234,50 TL</span></span></div>'
    assert r.parse_verified(html,offer('b','two'),'amazon')['price']==1234.5
    for broken in (html.replace('value="123"','value="999"'), html.replace('Stokta var',''), '<html>captcha</html>'):
        with pytest.raises(ValueError):r.parse_verified(broken,offer('b','two'),'amazon')

def test_failed_verification_never_writes(monkeypatch):
    monkeypatch.setattr(r,'fetch_verified',Mock(side_effect=ValueError('blocked')))
    with pytest.raises(ValueError):r.refresh_one(None,offer('b','two'),'n11',CUT,True)
    r.db.sb_patch.assert_not_called(); r.append_price_history.assert_not_called()

def test_preview_never_writes(monkeypatch):
    monkeypatch.setattr(r,'fetch_verified',Mock(return_value={'price':50,'currency':'TRY','in_stock':True}))
    r.refresh_one(None,offer('b','two'),'n11',CUT)
    r.db.sb_patch.assert_not_called(); r.append_price_history.assert_not_called()

def test_verified_updates_exact_offer_and_history(monkeypatch):
    monkeypatch.setattr(r,'fetch_verified',Mock(return_value={'price':50,'currency':'TRY','in_stock':True}))
    patch=Mock(); hist=Mock()
    monkeypatch.setattr(r.db,'sb_patch',patch);monkeypatch.setattr(r,'append_price_history',hist)
    r.refresh_one(None,offer('b','two'),'n11',CUT,True)
    assert patch.call_args.args[1]=={'id':'eq.b'}
    assert patch.call_args.args[2]['price']==50
    assert hist.call_args.args[0]['offer_id']=='b'

def test_suspicious_price_collapse_never_writes(monkeypatch):
    monkeypatch.setattr(r,'fetch_verified',Mock(return_value={'price':9,'currency':'TRY','in_stock':True}))
    with pytest.raises(ValueError,match='suspicious-price-drop'):
        r.refresh_one(None,offer('b','two'),'trendyol',CUT,True)
    r.db.sb_patch.assert_not_called(); r.append_price_history.assert_not_called()

def test_normal_discount_is_allowed():
    r.validate_price_change(offer('b','two'), 50)

def test_redirect_domain_checked_before_request():
    session=Mock();session.get.return_value=Mock(is_redirect=True,headers={'Location':'https://attacker.invalid'})
    with pytest.raises(ValueError):r.fetch_verified(session,offer('b','two'),'n11')
    assert session.get.call_count==1

def test_trendyol_product_group_verified():
    value={'@type':'ProductGroup','productGroupID':'123','sku':'123',
           'offers':{'@type':'Offer','price':'125.50',
                     'priceCurrency':'TRY',
                     'availability':'https://schema.org/InStock'}}
    html='<script type="application/ld+json">'+json.dumps(value)+'</script>'
    assert r.parse_verified(html,offer('b','two'),'trendyol')['price']==125.5

def test_trendyol_slug_redirect_with_same_product_id_allowed():
    redirect=Mock(is_redirect=True,headers={
        'Location':'https://www.trendyol.com/brand/new-slug-p-123'})
    final=Mock(is_redirect=False,text=page())
    session=Mock(); session.get.side_effect=[redirect,final]
    target=offer('b','two')
    target['product_url']='https://www.trendyol.com/brand/old-slug-p-123'
    assert r.fetch_verified(session,target,'trendyol')['price']==125.5

def test_browser_headers_are_full_browser_headers():
    assert 'Chrome/' in r.BROWSER_HEADERS['User-Agent']
    assert 'text/html' in r.BROWSER_HEADERS['Accept']

def test_mediamarkt_aggregate_offer_verified():
    value={'@type':'Product','name':'Device','sku':'123',
           'offers':{'@type':'AggregateOffer','lowPrice':'1599.90',
                     'priceCurrency':'TRY',
                     'availability':'https://schema.org/InStock'}}
    html='<script type="application/ld+json">'+json.dumps(value)+'</script>'
    target=offer('b','two')
    target['product_url']='https://www.mediamarkt.com.tr/tr/product/_device-123.html'
    assert r.parse_verified(html,target,'mediamarkt') == {
        'price':1599.9,'currency':'TRY','in_stock':True}

def test_redirect_to_different_product_path_rejected():
    redirect=Mock(is_redirect=True,headers={
        'Location':'https://www.n11.com/urun/other-999'})
    final=Mock(is_redirect=False,text=page())
    session=Mock(); session.get.side_effect=[redirect,final]
    with pytest.raises(ValueError,match='product-path-changed'):
        r.fetch_verified(session,offer('b','two'),'n11')

def test_pipeline_order():
    import run_pipeline
    assert [x[0] for x in run_pipeline.POST_STEPS]==['MATCH','REFRESH','DEAL']
