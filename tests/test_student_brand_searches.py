import contextlib
import io
from types import SimpleNamespace

import run_category_collector as collector
import run_pipeline


def test_brand_queries_keep_primary_category_filter():
    rows = run_pipeline.load_active_subcategories()
    laptop = next(row for row in rows if row["subcategory_slug"] == "laptop")
    assert laptop["filter_query"] == "laptop"
    assert "lenovo ideapad" in laptop["search_queries"]
    assert "apple macbook air" in laptop["search_queries"]


def test_brand_search_uses_laptop_filter_before_persistence():
    products = [
        {"title": "Lenovo IdeaPad Slim 3 15IRH8 Laptop"},
        {"title": "Lenovo IdeaPad 15 uyumlu laptop çantası"},
    ]
    saved = []
    module = SimpleNamespace(
        __name__="fake",
        LIMIT=20,
        collect=lambda **kwargs: products,
        save_products_to_supabase=lambda items: saved.extend(items),
    )
    with contextlib.redirect_stdout(io.StringIO()):
        result = collector.run_sync_collector(module, "lenovo ideapad", "laptop")
    assert result == 0
    assert saved == [products[0]]


def test_student_category_filters():
    cases = [
        ("usb bellek", "SanDisk Ultra Flair 128GB USB 3.0 Flash Bellek", True),
        ("usb bellek", "USB bellek kutusu taşıma çantası", False),
        ("bilimsel hesap makinesi", "Casio FX-991CW Bilimsel Hesap Makinesi", True),
        ("bilimsel hesap makinesi", "Bilimsel hesap makinesi kılıfı", False),
        ("okul çantası", "Eastpak Padded Pak'r Sırt Çantası", True),
        ("webcam", "Logitech C270 HD Webcam", True),
        ("webcam", "Webcam tripodu ve kapağı", False),
        ("çalışma masası lambası", "Xiaomi Mi LED Desk Lamp Pro", True),
        ("a4 fotokopi kağıdı", "Navigator Universal A4 80 gr 500 Yaprak Fotokopi Kağıdı", True),
        ("a4 fotokopi kağıdı", "A4 fotoğraf kağıdı parlak 50 yaprak", False),
    ]
    for query, title, expected in cases:
        assert collector.category_relevant(query, {"title": title})[0] is expected

NEW_CATEGORY_SLUGS = {
    "bebek-arabasi",
    "bebek-oto-koltugu",
    "bebek-telsizi-kamerasi",
    "gogus-pompasi",
    "biberon-sterilizatoru",
    "biberon-mama-isiticisi",
    "epilator",
    "sac-duzlestirici",
    "sac-masasi",
    "sac-kesme-makinesi",
    "kitap",
    "guvenlik-ip-kamerasi",
}


def test_new_shopping_categories_use_expected_store_matrix_and_brand_filters():
    rows = {
        row["subcategory_slug"]: row
        for row in run_pipeline.load_active_subcategories()
        if row["subcategory_slug"] in NEW_CATEGORY_SLUGS
    }
    assert set(rows) == NEW_CATEGORY_SLUGS
    assert rows["bebek-arabasi"]["stores"] == ["Trendyol", "Hepsiburada", "n11", "Amazon"]
    assert rows["bebek-telsizi-kamerasi"]["stores"] == ["Trendyol", "Hepsiburada", "n11", "MediaMarkt", "Amazon"]
    assert rows["epilator"]["stores"] == ["Trendyol", "Hepsiburada", "n11", "MediaMarkt", "Amazon"]
    assert rows["kitap"]["stores"] == ["Trendyol", "Hepsiburada", "n11", "Amazon"]
    assert rows["guvenlik-ip-kamerasi"]["stores"] == ["Trendyol", "Hepsiburada", "n11", "MediaMarkt", "Vatan", "Amazon"]
    for row in rows.values():
        assert row["filter_query"] == row["query"]
    assert "chicco bebek arabası" in rows["bebek-arabasi"]["search_queries"]
    assert "braun silk epil" in rows["epilator"]["search_queries"]
    assert "tp link tapo kamera" in rows["guvenlik-ip-kamerasi"]["search_queries"]


def test_new_shopping_category_filters_accept_products_and_reject_accessories():
    cases = [
        ("bebek arabası", "Chicco Goody Plus Bebek Arabası", True),
        ("bebek arabası", "Bebek arabası için yağmur örtüsü", False),
        ("bebek oto koltuğu", "Cybex Sirona T Bebek Oto Koltuğu", True),
        ("bebek oto koltuğu", "Bebek oto koltuğu koruyucu kılıf", False),
        ("bebek oto koltuğu", "Joie i-Spin Oto Koltuğu Isofix Baza Dahil", True),
        ("bebek telsizi", "Motorola VM35 Bebek Kamerası ve Telsizi", True),
        ("bebek telsizi", "Bebek monitörü duvar aparatı", False),
        ("bebek telsizi", "Motorola VM35 Connect Adaptör Dahil", True),
        ("göğüs pompası", "Philips Avent Elektrikli Göğüs Pompası Biberonlu", True),
        ("göğüs pompası", "Göğüs pompası yedek valf ve hortum seti", False),
        ("biberon sterilizatörü", "Philips Avent Buharlı Biberon Sterilizatörü", True),
        ("biberon sterilizatörü", "Philips Avent SCF291/00 Premium Sterilizatör", True),
        ("biberon sterilizatörü", "Sterilizatör için yedek parça", False),
        ("biberon mama ısıtıcı", "Chicco Home Biberon ve Mama Isıtıcı", True),
        ("biberon mama ısıtıcı", "Biberon ısıtıcı için taşıma çantası", False),
        ("epilatör", "Braun Silk-epil 9 Epilatör", True),
        ("epilatör", "Braun epilatör yedek başlık", False),
        ("saç düzleştirici", "Remington S9500 Saç Düzleştirici", True),
        ("saç düzleştirici", "Saç düzleştirici ısıya dayanıklı mat", False),
        ("saç maşası", "Babyliss C325E Saç Maşası", True),
        ("saç maşası", "Saç maşası için koruyucu kılıf", False),
        ("saç kesme makinesi", "Wahl Color Pro Saç Kesme Makinesi", True),
        ("saç kesme makinesi", "Saç kesme makinesi yedek bıçak", False),
        ("kitap", "Kürk Mantolu Madonna Roman Ciltsiz Kitap", True),
        ("kitap", "Simyacı Paulo Coelho Can Yayınları", True),
        ("kitap", "Masaüstü metal kitap standı", False),
        ("güvenlik ip kamerası", "TP-Link Tapo C210 Wi-Fi IP Güvenlik Kamerası", True),
        ("güvenlik ip kamerası", "IP kamera duvar montaj aparatı", False),
    ]
    for query, title, expected in cases:
        result, reason = collector.category_relevant(query, {"title": title})
        assert result is expected, (query, title, reason)
