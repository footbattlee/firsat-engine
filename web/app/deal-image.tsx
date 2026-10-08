"use client";
import { useState } from "react";
export function DealImage({ src, title, hero = false }: { src: string | null; title: string; hero?: boolean }) {
 const [failed, setFailed] = useState(false);
 return src && !failed
  ? <img src={src} alt={title} loading={hero ? "eager" : "lazy"} decoding="async" onError={() => setFailed(true)} />
  : <div className="imageFallback" role="img" aria-label={title + " — ürün görseli bulunmuyor"}><span>✦</span><small>Ürün görseli hazırlanıyor</small></div>;
}
