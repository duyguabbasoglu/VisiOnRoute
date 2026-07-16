import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "VISiOnRoute",
    template: "%s | VISiOnRoute",
  },
  description:
    "Sürücü davranışlarını ve yol koşullarını gerçek zamanlı analiz ederek riskleri oluşmadan görünür kılan ulaşım güvenliği platformu.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr">
      <body>{children}</body>
    </html>
  );
}
