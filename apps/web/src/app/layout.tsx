import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/lib/providers";

const DESCRIPTION =
  "Sürücü davranışlarını ve yol koşullarını gerçek zamanlı analiz ederek riskleri oluşmadan görünür kılan ulaşım güvenliği platformu.";

// Absolute base for social-preview URLs; Vercel provides the production host.
const SITE_URL = process.env.VERCEL_PROJECT_PRODUCTION_URL
  ? `https://${process.env.VERCEL_PROJECT_PRODUCTION_URL}`
  : "http://localhost:3000";

// Icons (favicon.ico, icon.png, apple-icon.png) and the social preview image
// (opengraph-image.png) live next to this file and are wired up by Next.js.
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  applicationName: "VisiOnRoute",
  title: {
    default: "VisiOnRoute",
    template: "%s | VisiOnRoute",
  },
  description: DESCRIPTION,
  openGraph: {
    type: "website",
    siteName: "VisiOnRoute",
    locale: "tr_TR",
    title: "VisiOnRoute",
    description: DESCRIPTION,
  },
  twitter: { card: "summary_large_image", title: "VisiOnRoute", description: DESCRIPTION },
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
