"""Offline regression coverage; network access is forbidden in every test."""
import json
import sys
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'matching'))
sys.path.insert(0, str(ROOT))
import product_matcher as m
import apply_matches as writer
import run_category_collector as collector


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError('Regression tests must not access the network')
    monkeypatch.setattr(m, 'urlopen', denied)
    monkeypatch.setattr(writer, 'urlopen', denied)
    monkeypatch.setattr(urllib.request, 'urlopen', denied)
    monkeypatch.setattr(m, 'MIN_SCORE', 75)
    monkeypatch.setattr(writer, 'AUTO_APPROVE_MIN', 88)
    monkeypatch.setattr(m, 'VOLUME_TOLERANCE_ML', 5)
    monkeypatch.delenv('PRODUCT_LIMIT', raising=False)


def row(title, brand='Stanley', merchant='a', **extra):
    return {'title': title, 'brand': brand, 'merchant_id': merchant,
            'merchant': merchant, 'product_id': merchant, 'gtin': None,
            'price': 100, 'currency': 'TRY', **extra}


@pytest.mark.parametrize('title,expected', [
    ('Termos 1.9 Litre', 1900), ('Termos 1,9 lt', 1900),
    ('Termos 1900 ml', 1900), ('Termos .47L 16oz', 470),
    ('Termos 0.47', 470), ('Termos 16 oz', 473),
    ('Samsung 1.9 Model', None),
])
def test_capacity(title, expected):
    assert m.extract_volume_ml(title) == expected


@pytest.mark.parametrize('other,reason', [
    ('Stanley Classic Vakumlu Termos 1.4 L', 'volume-conflict'),
    ('Stanley Classic Vakumlu Termos 1.9 L Yedek Kapak', 'accessory-conflict'),
    ('Stanley Classic Vakumlu Termos 1.9 L Kılıfı', 'accessory-conflict'),
])
def test_thermos_negatives(other, reason):
    assert m.pair_score(row('Stanley Classic 1.9 Litre Vakumlu Termos'), row(other, merchant='b')) == (0, reason)


def test_stanley_family_not_global_threshold_relaxation():
    a = row('Stanley Classic 1.9 Litre Vakumlu Termos')
    b = row('STANLEY Classic Legendary Vakumlu Termos 1.9 Litre - Yeşil (Hammertone Green) | Paslanmaz Çelik', merchant='b')
    assert m.pair_score(a, b) == (90, 'drinkware-family-capacity')
    assert m.pair_score(a, row('Stanley Adventure Vakumlu Termos 1.9 L', merchant='b'))[0] < 88
    assert m.pair_score(a, row('Stanley Classic Vakumlu Yemek Termosu 1.9 L', merchant='b'))[0] < 88
    assert m.pair_score(a, row('Stanley Classic Vakumlu Termos', merchant='b'))[0] < 88


def test_iceflow_generations_do_not_merge():
    a = row('Stanley Iceflow Flip Straw Termos 0.89 L')
    b = row('Stanley Iceflow Flip Straw 2.0 Termos 0.89 L', merchant='b')
    assert m.pair_score(a, b) == (0, 'drinkware-family-conflict')


@pytest.mark.parametrize('a,b,brand', [
    ('Enjoy Biftekli Yetişkin Köpek Maması 15 Kg', 'Biftekli Yetişkin Köpek Maması 15000 gr Fiyatları ve Özellikleri', 'Enjoy'),
    ("L'Oreal Paris True Match Bakım Yapan Fondöten - 1.5N Nötr Alt Ton", 'True Match Bakım Yapan Fondöten - 1.5N Nötr Alt Ton', "L'Oreal Paris"),
    ('Sleepy Natural Double Soft Bebek Bezi 5 Numara 156 Adet', 'Natural Double Soft Bebek Bezi 5 Numara 156 Adet Fiyatları ve Özellikleri', 'Sleepy'),
    ('Magly Manyetik Yapı Blokları 72 Parça Oyun Seti', 'Manyetik Yapı Blokları 72 Parça Oyun Seti Fiyatları ve Özellikleri', 'Magly'),
    ('Tefal Ingenio Ceramic Renew İndüksiyon 3 Parça Tava Seti', 'Ingenio Ceramic Renew İndüksiyon 3 Parça Tava Seti', 'Tefal'),
])
def test_exact_identity_across_categories(a, b, brand):
    assert m.pair_score(row(a, brand), row(b, brand, 'b')) == (92, 'exact-normalized-title')


@pytest.mark.parametrize('a,b,brand', [
    ('True Match Fondöten 1.5N', 'True Match Fondöten 1.5W', 'Loreal'),
    ('True Match Fondöten 1.5N', 'True Match Fondöten 15N', 'Loreal'),
    ('Kalıcı Ruj 004 Rose', 'Kalıcı Ruj 005 Rose', 'Flormar'),
    ('Baked Blush On Fırınlanmış Allık', 'Baked Blush On Fırınlanmış Allık', 'Flormar'),
    ('Biftekli Köpek Maması 15 kg', 'Kuzulu Köpek Maması 15 kg', 'Enjoy'),
    ('Biftekli Köpek Maması 15 kg', 'Biftekli Köpek Maması 10 kg', 'Enjoy'),
    ('Natural Bebek Bezi 5 Numara 156 Adet', 'Natural Bebek Bezi 6 Numara 156 Adet', 'Sleepy'),
    ('Natural Bebek Bezi 5 Numara 156 Adet', 'Natural Bebek Bezi 5 Numara 124 Adet', 'Sleepy'),
    ('Yapı Blokları 72 Parça Set', 'Yapı Blokları 36 Parça Set', 'Magly'),
    ('iPhone 17 Pro 256 GB Telefon', 'iPhone 17 Pro 512 GB Telefon', 'Apple'),
    ('iPhone 17 Pro 256 GB Telefon', 'iPhone 17 Pro Max 256 GB Telefon', 'Apple'),
    ('JBL Foo IP67 Bluetooth Hoparlör', 'JBL Bar IP67 Bluetooth Hoparlör', 'JBL'),
    ('Photoderm SPF50 Güneş Kremi 150ml', 'Photoderm SPF50 Bronzlaştırıcı Krem 150ml', 'Bioderma'),
    ('Philips MG9532/15 15in1 Tıraş Makinesi', 'Philips MG9532/15 16in1 Tıraş Makinesi', 'Philips'),
])
def test_critical_negative_variants(a, b, brand):
    assert m.pair_score(row(a, brand), row(b, brand, 'b'))[0] < 88


def test_one_sided_model_stays_conservative():
    a = row('Stanley Transit Fliptop Mug 0.47 L 10-13062-012')
    b = row('Stanley Transit Fliptop Mug 0.47 L', merchant='b')
    assert m.pair_score(a, b) == (0, 'model-missing-one-side')


def test_gtin_candidates_without_brand_and_padding():
    rows = [row('Product A', None, gtin='036000291452'),
            row('Product B', None, 'b', gtin='0036000291452')]
    assert m.valid_gtin(rows[0]['gtin']) == m.valid_gtin(rows[1]['gtin'])
    assert m.pair_score(*rows) == (100, 'gtin')
    assert len(m.build_groups(rows, min_score=88)) == 1
    assert m.valid_gtin('0000000000000') is None
    assert m.valid_gtin('036000291453') is None


def test_gtin_conflict_and_contradictory_capacity():
    a = row('Stanley Classic Vakumlu Termos 1.9 L', gtin='6939236347587')
    b = row(a['title'], merchant='b', gtin='6939236347594')
    assert m.pair_score(a, b) == (0, 'gtin-conflict')
    b.update(gtin=a['gtin'], title='Stanley Classic Vakumlu Termos 1.4 L')
    assert m.pair_score(a, b) == (0, 'gtin-volume-conflict')


def test_catalog_brand_inference_is_supported_and_non_mutating():
    rows = [row('Stanley Classic Termos 1 L'), row('Stanley Classic Termos 1 L', merchant='b'),
            row('STANLEY Classic Termos 1 L', None, 'c'),
            row('Stanley uyumlu termos kılıfı', None, 'd'),
            row('Stanley Classic Termos 1 L', 'OtherMaker', 'e')]
    result = m.prepare_rows(rows)
    assert result[2]['brand'] == 'Stanley' and rows[2]['brand'] is None
    assert result[3]['brand'] is None
    assert result[4]['brand'] == 'OtherMaker'
    assert m.prepare_rows([rows[0], rows[2]])[1]['brand'] is None


def test_ambiguous_brand_prefix_fails_closed():
    rows = [row('X', 'Philips', 'a'), row('X', 'Philips', 'b'),
            row('X', 'Philips Avent', 'a'), row('X', 'Philips Avent', 'b'),
            row('Philips Avent Biberon 200ml', None, 'c')]
    assert m.prepare_rows(rows)[-1]['brand'] is None


def test_complete_linkage_and_approval_threshold(monkeypatch):
    rows = [row('A', merchant='a'), row('B', merchant='b'), row('C', merchant='c')]
    scores = {('A', 'B'): 99, ('A', 'C'): 80, ('B', 'C'): 80}
    monkeypatch.setattr(m, 'pair_score', lambda a,b: (scores[tuple(sorted((a['title'],b['title'])))], 'fixture'))
    low = m.build_groups(rows)
    assert len(low[0][1]) == 3
    assert writer.plan_group(*low[0], rows, [])['action'] == 'review'
    high = m.build_groups(rows, min_score=88)
    assert high[0][1] == [0,1]
    monkeypatch.setitem(scores, ('B','C'), 0)
    assert all(len(idx) < 3 for _,idx,_ in m.build_groups(rows))


def test_existing_canonical_guards():
    rows = [row('Stanley Classic Vakumlu Termos 1.9 L', merchant='a'),
            row('Stanley Classic Vakumlu Termos 1.9 L', merchant='b'),
            row('Stanley Classic Vakumlu Termos 1.4 L', merchant='c')]
    group = (90, [0,1], [(90,'fixture',0,1)])
    existing = [{'product_id':'a','canonical_product_id':'cid','status':'approved'}]
    assert writer.plan_group(*group, rows, existing)['action'] == 'attach'
    assert writer.plan_group(*group, rows, existing + [{'product_id':'c','canonical_product_id':'cid','status':'approved'}])['reason'] == 'canonical-member-incompatible'
    assert writer.plan_group(*group, rows, existing + [{'product_id':'missing','canonical_product_id':'cid','status':'approved'}])['reason'] == 'canonical-member-outside-snapshot'
    assert writer.plan_group(*group, rows, existing + [{'product_id':'b','canonical_product_id':'other','status':'approved'}])['reason'] == 'canonical-conflict'
    assert writer.plan_group(*group, rows, [{**existing[0], 'status':'rejected'}])['reason'] == 'existing-nonapproved-match'


def test_dry_run_never_writes(tmp_path, monkeypatch):
    rows = [row('Stanley Classic Vakumlu Termos 1.9 L'), row('Stanley Classic Vakumlu Termos 1.9 L', merchant='b')]
    infile = tmp_path/'input.json'; report = tmp_path/'report.json'
    infile.write_text(json.dumps({'rows':rows,'matches':[]}), encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['apply_matches.py','--dry-run','--input',str(infile),'--report',str(report)])
    monkeypatch.setattr(writer, 'sb', lambda *a,**k: pytest.fail('production call'))
    monkeypatch.setattr(writer, 'sb_get', lambda *a,**k: pytest.fail('production call'))
    writer.main()
    result = json.loads(report.read_text(encoding='utf-8'))
    assert result['new_canonicals'] == 1 and result['new_product_matches'] == 2


@pytest.mark.parametrize('value', ['0','-1','oops'])
def test_invalid_collector_limit(value, monkeypatch):
    monkeypatch.setenv('PRODUCT_LIMIT', value)
    with pytest.raises(ValueError): collector.collector_limit(SimpleNamespace(LIMIT=20))


def test_async_and_sync_limits(monkeypatch):
    monkeypatch.setenv('PRODUCT_LIMIT','50')
    seen=[]
    async def main(): seen.append(module.LIMIT)
    module=SimpleNamespace(LIMIT=20,main=main)
    collector.run_async_collector(module,'termos')
    assert seen == [50]
    collect=Mock(return_value=[])
    module=SimpleNamespace(__name__='fake',LIMIT=20,collect=collect,save_products_to_supabase=Mock())
    collector.run_sync_collector(module,'termos')
    collect.assert_called_once_with(query='termos',limit=50)


def test_real_catalog_fixtures():
    fixtures=json.loads((ROOT/'tests/fixtures/matching_catalog_pairs.json').read_text(encoding='utf-8'))
    for case in fixtures:
        a,b=case['a'],case['b']
        assert (m.pair_score(a,b)[0] >= 88) == case['expected'], case['label']


def test_model_dot_suffix_is_not_discarded():
    a=row("Delonghi Dedica Duo EC890.GR Espresso Kahve Makinesi", "Delonghi")
    b=row("Delonghi Dedica Duo EC890.PK Espresso Kahve Makinesi", "Delonghi", "b")
    assert m.pair_score(a,b) == (0, "tech-explicit-model-conflict")


def test_real_model_retains_known_consumer_family():
    a=row("Anker Soundcore Q20i Kulaklık", "Anker")
    b=row("Anker Soundcore Q20i A3004 Kulaklık", "Anker", "b")
    assert m.pair_score(a,b)[0] >= 88


def test_pagination_has_stable_order(monkeypatch):
    calls=[]
    class Response:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self): return b"[]"
    monkeypatch.setattr(m,"SUPABASE_SERVICE_ROLE_KEY","test-only")
    monkeypatch.setattr(m,"urlopen",lambda req,**kwargs: (calls.append(req.full_url) or Response()))
    assert m.sb_get("products") == []
    assert "order=id" in calls[0]


@pytest.mark.parametrize("a,b", [
    ("Philips Aqua Trio XW9463/11 Dikey Süpürge", "Philips Aqua Trio XW9463/11 Dikey Süpürge ve Philips Solüsyon XV1792/01"),
    ("Canon Pixma G3470 Yazıcı", "Canon Pixma G3470 Yazıcı + Fotoğraf Kağıdı Hediyeli"),
    ("Sinbo SK-8030 Kettle", "Sinbo SK-8030 Kettle (SK-7338)"),
])
def test_bundle_and_extra_model_guards(a,b):
    assert m.pair_score(row(a,"Brand"),row(b,"Brand","b"))[0] < 88


@pytest.mark.parametrize("a,b", [
    ("iPhone 17 Pro 256 GB", "iPhone 17 Pro 512 GB"),
    ("iPhone 17 Pro 256 GB", "iPhone 17 Pro Max 256 GB"),
    ("Canon G3470 Yazıcı", "Canon G3470 Yazıcı + Kağıt Hediyeli"),
])
def test_same_gtin_does_not_override_explicit_critical_variants(a,b):
    assert m.pair_score(row(a,"Brand",gtin="036000291452"),
                        row(b,"Brand","b",gtin="036000291452"))[0] == 0



def test_explicit_approval_threshold_cannot_lower_configured_minimum(monkeypatch):
    monkeypatch.setattr(m, "MIN_SCORE", 95)
    rows=[row("Stanley Classic Vakumlu Termos 1.9 L"), row("Stanley Classic Vakumlu Termos 1.9 L", merchant="b")]
    assert m.build_groups(rows,min_score=88) == []


def test_audit_price_gap_uses_second_store_and_same_currency():
    import audit_matches as audit
    rows=[row("X",merchant="a",product_id="p1",price=50),
          row("X",merchant="a",product_id="p2",price=60),
          row("X",merchant="b",product_id="p3",price=100),
          row("X",merchant="c",product_id="p4",price=1,currency="USD")]
    matches=[{"product_id":r["product_id"],"canonical_product_id":"cid","status":"approved"} for r in rows]
    counts=audit.price_gap_funnel(rows,matches)
    assert counts["cross_store"] == 1 and counts["gap_at_least_15_percent"] == 1
    assert counts["single_store"] == 1


def test_same_merchant_never_matches():
    a=row("Stanley Classic Vakumlu Termos 1.9 L",gtin="036000291452")
    assert m.pair_score(a,dict(a)) == (0,"same-merchant")
