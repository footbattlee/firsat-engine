import Link from "next/link";
export function SiteHeader() {
 return <header className="siteHeader"><div className="shell catalogueHeader">
 <Link className="logo" href="/" aria-label="Fırsatcı ana sayfa"><span className="logoSymbol" aria-hidden="true">f</span>fırsatcı<span className="logoDot">.</span></Link>
 <nav aria-label="Ana menü"><Link href="/#kategoriler">Kategoriler</Link><Link href="/#firsatlar">Tüm fırsatlar</Link><Link href="/#nasil">Nasıl çalışır?</Link></nav>
 <span className="headerNote">İyi fiyatın peşinde.</span></div></header>;
}
export function SiteFooter() {
 return <footer className="siteFooter"><div className="shell"><a className="logo" href="/">fırsatcı<span className="logoDot">.</span></a>
 <p>İyi fiyatın peşinde.</p><div className="footerBottom"><span>© {new Date().getFullYear()} Fırsatcı</span>
 <p>Anonim ziyaret ve bağlantı sayaçları tutulur; ham IP adresi saklanmaz. Bazı bağlantılar gelir ortaklığı bağlantısıdır.
 Fiyat, stok ve koşullar mağazada değişebilir. Rakip fiyatı eski fiyat değildir.</p></div></div></footer>;
}
