/** Turkish-aware text helpers and client-side validation mirrors. */

const TR_MAP: Record<string, string> = {
  ç: "c",
  Ç: "c",
  ğ: "g",
  Ğ: "g",
  ı: "i",
  I: "i",
  İ: "i",
  ö: "o",
  Ö: "o",
  ş: "s",
  Ş: "s",
  ü: "u",
  Ü: "u",
};

/** Organization short name suggestion matching the backend slug pattern. */
export function slugify(value: string): string {
  const ascii = value
    .split("")
    .map((ch) => TR_MAP[ch] ?? ch)
    .join("")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return ascii.slice(0, 80).replace(/-+$/g, "");
}

export const SLUG_PATTERN = /^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$/;

/** Mirrors visionroute.domain.passwords so users get feedback before submitting. */
export function passwordProblems(password: string): string[] {
  const problems: string[] = [];
  if (password.length < 12) problems.push("Parola en az 12 karakter olmalıdır.");
  if (/^\d+$/.test(password) || /^\p{L}+$/u.test(password)) {
    problems.push("Parola harf ve rakam (veya sembol) karışımı içermelidir.");
  }
  return problems;
}

/** Read `#token=...` from the URL once and remove it from the address bar/history. */
export function consumeFragmentToken(): string | null {
  if (typeof window === "undefined") return null;
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const token = params.get("token");
  if (window.location.hash) {
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
  }
  return token;
}
