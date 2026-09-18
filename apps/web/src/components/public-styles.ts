/**
 * Call-to-action classes for the public pages. Kept out of the "use client"
 * PublicSite module so server components can import plain strings.
 */
const CTA_BASE =
  "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-ink-900";

export const CTA_STYLES = {
  primary: `${CTA_BASE} bg-brand-500 text-white shadow-lg shadow-brand-900/40 hover:bg-brand-600 focus-visible:ring-brand-500`,
  secondary: `${CTA_BASE} border border-white/15 bg-white/5 text-white hover:bg-white/10 focus-visible:ring-white/50`,
  ghost: `${CTA_BASE} text-slate-200 hover:bg-white/10 hover:text-white focus-visible:ring-white/50`,
  amber: `${CTA_BASE} bg-amber-400 text-ink-900 hover:bg-amber-300 focus-visible:ring-amber-300`,
} as const;
