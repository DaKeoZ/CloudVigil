import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "CloudVigil — Monitoring Cloud",
  description: "Tableau de bord de monitoring cloud en temps réel",
  icons: { icon: "/favicon.ico" },
};

export const viewport: Viewport = {
  themeColor: "#020617",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" className={`dark ${inter.variable}`}>
      <body>{children}</body>
    </html>
  );
}
