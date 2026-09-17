import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Fırsatlar | PlayFootBattle",
  description: "Türkiye'deki mağazalarda fiyatları karşılaştır, gerçek fırsatları keşfet.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr">
      <body>{children}</body>
    </html>
  );
}
