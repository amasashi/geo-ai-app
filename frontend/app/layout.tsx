import type { Metadata } from "next";
import type { ReactNode } from "react";
import "leaflet/dist/leaflet.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "GeoAI Map",
  description: "国土交通省MCPサーバーの地理空間データを地図に表示するアプリ"
};

export default function RootLayout({
  children
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="ja" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
