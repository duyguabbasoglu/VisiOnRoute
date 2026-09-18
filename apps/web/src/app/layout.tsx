import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/lib/providers";

export const metadata: Metadata = {
  title: {
    default: "VisiOnRoute",
    template: "%s | VisiOnRoute",
  },
  description:
    "Sürücü davranışlarını ve yol koşullarını gerçek zamanlı analiz ederek riskleri oluşmadan görünür kılan ulaşım güvenliği platformu.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
