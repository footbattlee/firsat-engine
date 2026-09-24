import contextlib
import importlib.util
import io
import json
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


candidate = load('category_collector_under_test', ROOT.parent / 'run_category_collector.py')
fixtures = json.loads(ROOT.joinpath('fixtures/amazon_82_category_titles.json').read_text(encoding='utf-8'))
FOCUS = {
    'oyuncu kulakligi',
    'akilli bileklik',
    'dikey supurge',
    'sarjli matkap',
    'arac kamerasi',
    'tablet',
    'yazici',
    'tiras makinesi',
    'elektrikli dis fircasi',
    'hava temizleyici',
}

CASES = {
    'oyuncu kulaklığı': {
        True: ['Razer BlackShark V2 X', 'SteelSeries Arctis Nova 7', 'JBL Quantum 360', 'Gaming mikrofonlu kulaklık', 'RAZER BLACKSHARK V2 X ESPORTS KULAKLIK', 'Oyun kulaklığı + taşıma kılıfı'],
        False: ['Razer BlackShark V2 X yedek ped', 'SteelSeries Arctis Nova ear pads', 'JBL Quantum 360 replacement cable', 'Gaming headset stand', 'Oyuncu kulaklığı kılıfı', 'JBL Bluetooth hoparlör', 'Oyuncu klavyesi', 'Razer BlackShark mikrofonu', 'Gaming headset case + stand'],
    },
    'akıllı bileklik': {
        True: ['HUAWEI Band 10 Akıllı Saat', 'WHOOP Peak 5.0', 'Google Fitbit Air', 'Akıllı takip bilekliği', 'Nilox ONAIR akıllı bant', 'Xiaomi Smart Band 10 + kayış'],
        False: ['HUAWEI Band 10 kayış', 'WHOOP Peak replacement strap', 'Xiaomi Mi Band 8 kordon', 'Fitbit Air şarj kablosu', 'Smart band screen protector', 'HUAWEI WATCH GT 6 Pro akıllı saat', 'Redmi Watch 5 Lite', 'Wiky Watch çocuk saati', 'HUAWEI Band 10 silikon kılıf', 'WHOOP Peak wristband'],
    },
    'dikey süpürge': {
        True: ['YUI Dikey Elektrikli Süpürge HEPA Filtreli', 'Fakir Kablolu Dik Süpürge', 'Dikey Elektrik Süpürgesi', 'Kablosuz Dik Süpürge', 'Cordless stick vacuum cleaner', 'Şarjlı dikey süpürge + yedek filtre'],
        False: ['Roborock S9 Robot Süpürge', 'Karcher VCC 4 CycloneX', 'Dikey süpürge filtresi', 'Dikey süpürge yedek batarya', 'Dikey süpürge fırçası', 'Dikey süpürge şarj cihazı', 'Dikey süpürge HEPA filtre seti', 'Dikey süpürge HEPA filtre', '25V dikey süpürge uyumlu turbo başlık', 'Cordless stick vacuum replacement filter', 'Robot dikey süpürge aksesuarı'],
    },
    'şarjlı matkap': {
        True: ['Akülü Darbeli Matkap Seti', 'WORX Kömürsüz Şarjlı Darbeli Matkap', 'Bosch GSB 185-LI', 'Bosch GSR 18V-50 LI', 'Şarjlı matkap + batarya + şarj cihazı', 'Şarjlı matkap + 24 uç seti'],
        False: ['Bosch GSB 185-LI batarya', 'Akülü matkap şarj cihazı', 'Şarjlı matkap ucu', 'Vidalama uç seti', 'Cordless drill bits', 'Bosch GSB 185-LI mandren', 'Bosch GSB 185-LI şarj cihazı + batarya'],
    },
    'araç kamerası': {
        True: ['AZDOME S50 Araç İçi Kamera (Obd Park Kiti)', 'Botslab araç içi kamera', 'Dashcam', 'Araç kamerası + 32GB hafıza kartı', '4K+2K Araç Kamerası', '70mai A500s DashCam Pro Plus+ Araç İçi Kamera'],
        False: ['Araç kamerası hardwire kit kablosu', 'Dashcam mounting bracket', 'Araç kamerası hafıza kartı', 'AZDOME araç kamerası montaj kiti', 'Araç tutacağı ve hardwire kit kablosu hediye', 'Ev güvenlik kamerası', 'Araç kamerası kablosu + montaj kiti'],
    },
    'tablet': {
        True: ['Casper PAD H10 PEN 12.6 OLED Tablet 8GB RAM 256GB+Casper H10 Tablet Kılıfı + Prestige Kalem', 'Lenovo 8GB Tablet+Kalem+Kılıf', 'Samsung Galaxy Tab A11', 'Redmi Pad 2 8+128GB', 'Tablet 8GB RAM 128GB - Kılıf ve kalem hediyeli', 'Chuwi 12GB RAM Kılıf Kalem ve Klavyeli Tablet', 'Android Tablet PC 128GB kılıf, fare, kalem'],
        False: ['Samsung Galaxy Tab Tablet Kılıfı', 'Samsung Galaxy Tab A11 128GB uyumlu kılıf', 'iPad 9.Nesil 10.2 ekran koruyucu', 'Tablet standı', 'iPad case + kalem', 'Tablet kılıfı + kalem hediyeli', 'Tablet PC için kılıf 128GB modeli', 'Tablet 8GB 128GB kılıf', 'Redmi Pad 2 8+128GB uyumlu kılıf', 'Tablet şarj kablosu'],
    },

'yazici': {
    True: [
        'Canon PIXMA TS3750i Siyah',
    ],
    False: [
        'Canon PIXMA uyumlu siyah murekkep kartusu',
    ],
},
'tiras makinesi': {
    True: [
        'SINBO SHC-1903 T-Bicakli Sac Sakal Kesme Makinesi',
        'Braun Hepsi Bir Arada Series 7 11i 1 arada Tiras Kiti AIO7540',
        'Braun Sakal Duzeltici Series 7 BT7540',
        'TR-3100 Sac Sakal Kesim Makinesi',
        'Philips OneBlade hibrit tiras makinesi yedek bicak dahil',
    ],
    False: [
        'Philips OneBlade yedek bicak 2 li paket',
    ],
},
'elektrikli dis fircasi': {
    True: [
        'Oral-B iO Sense ile iO - 10 Siyah Elektrikli Sarjli Dis Fircasi',
        'Philips Sonicare 3100 Sonic Sarjli Dis Fircasi 2 li Paket',
        'NPO Nicefeel X610-Z Sarjli Sonic Profesyonel Dis Fircasi',
        'Oral-B Profesyonel Temizlik 1 Sarj Edilebilir Dis Fircasi',
        'Oral-B iO9 elektrikli dis fircasi yedek baslik dahil',
    ],
    False: [
        'Philips Sonicare Power Flosser 3000 Kablosuz Agiz Dusu',
        'Oral-B iO yedek firca basligi 4 lu',
    ],
},
'hava temizleyici': {
    True: [
        'Philips 8000 Serisi Air Performer 3in1 Hava Temizleme Cihazi',
        'Dijitsu Ht 300 Hava Temizleme Cihazi',
        'Havit HAP108 Hava Temizleme Cihazi 3 Katmanli Gercek HEPA Filtreli',
        'LG Puricare 360 Air Purifier Double Hava Temizleme Cihazi',
        'EZERE Ev Ofis icin Ultrasonik Hava Temizleyici Kotu Koku Giderme Cihazi',
    ],
    False: [
        'Philips 1000 Serisi Hava Nemlendirici',
        'Xiaomi Hava Nemlendirici 2 Lite',
        'Robeve Hava Temizleyici Nemlendirici Aroma Difuzoru',
        'Philips hava temizleyici uyumlu filtre seti',
    ],
},
}

class FilterTests(unittest.TestCase):
    def test_log_replay(self):
        counts = {}
        for row in fixtures:
            q = candidate.normalize_text(row['query'])
            got = candidate.category_relevant(q, row)[0]
            if q not in FOCUS:
                self.assertEqual(list(candidate.category_relevant(q, row)), row['unchanged_result'])
                continue
            expected = row['expected']
            with self.subTest(query=q, title=row['title']):
                self.assertEqual(got, expected, candidate.category_relevant(q, row))
            count = counts.setdefault(q, Counter())
            count['total'] += 1
            count['before'] += row['old_accept']
            count['after'] += got
        print('REPLAY_COUNTS', json.dumps(counts, ensure_ascii=False))

    def test_counterexamples_and_bundles(self):
        for query, outcomes in CASES.items():
            for expected, titles in outcomes.items():
                for title in titles:
                    with self.subTest(query=query, title=title):
                        self.assertEqual(candidate.category_relevant(query, {'title': title})[0], expected)

    def test_empty_unknown_and_bluetooth_local_rule(self):
        for title in [None, '', '   ']:
            self.assertEqual(candidate.category_relevant('tablet', {'title': title}), (False, 'empty-title'))
        self.assertEqual(candidate.category_relevant('unknown', {'title': 'Tablet'}), (False, 'category-rule-missing'))
        self.assertEqual(candidate.category_relevant('bluetooth kulaklık', {'title': 'Bluetooth kulaklık kılıfı'})[0], False)

    def test_before_persistence(self):
        products = [{'title': 'Huawei Band 10'}, {'title': 'Huawei Band 10 kayış'}]
        saved = []
        collector = SimpleNamespace(__name__='fake', LIMIT=20, collect=lambda **kwargs: products,
                                    save_products_to_supabase=lambda items: saved.extend(items))
        with contextlib.redirect_stdout(io.StringIO()):
            result = candidate.run_sync_collector(collector, 'akıllı bileklik')
        self.assertEqual(result, 0)
        self.assertEqual(saved, [products[0]])


if __name__ == '__main__':
    unittest.main(verbosity=2)
