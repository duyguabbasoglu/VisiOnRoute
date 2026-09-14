import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { MAIL_DIR } from "./env";

export interface ReceivedEmail {
  to: string;
  subject: string;
  text: string;
  file: string;
}

function splitHeaders(raw: string): { headers: Map<string, string>; body: string } {
  const normalized = raw.replace(/\r\n/g, "\n");
  const index = normalized.indexOf("\n\n");
  const head = index === -1 ? normalized : normalized.slice(0, index);
  const body = index === -1 ? "" : normalized.slice(index + 2);
  const headers = new Map<string, string>();
  for (const line of head.replace(/\n[ \t]+/g, " ").split("\n")) {
    const colon = line.indexOf(":");
    if (colon > 0) headers.set(line.slice(0, colon).trim().toLowerCase(), line.slice(colon + 1).trim());
  }
  return { headers, body };
}

function decodeQuotedPrintable(value: string): string {
  const bytes: number[] = [];
  const joined = value.replace(/=\n/g, "");
  for (let i = 0; i < joined.length; i += 1) {
    const char = joined.charAt(i);
    if (char === "=" && /^[0-9A-Fa-f]{2}$/.test(joined.slice(i + 1, i + 3))) {
      bytes.push(parseInt(joined.slice(i + 1, i + 3), 16));
      i += 2;
    } else {
      bytes.push(...Buffer.from(char, "utf8"));
    }
  }
  return Buffer.from(bytes).toString("utf8");
}

function decodeEncodedWords(value: string): string {
  return value.replace(/=\?([^?]+)\?([bqBQ])\?([^?]*)\?=/g, (_match, _charset: string, encoding: string, text: string) =>
    encoding.toLowerCase() === "b"
      ? Buffer.from(text, "base64").toString("utf8")
      : decodeQuotedPrintable(text.replace(/_/g, " ")),
  );
}

function decodeBody(body: string, encoding: string | undefined): string {
  switch ((encoding ?? "7bit").toLowerCase()) {
    case "base64":
      return Buffer.from(body.replace(/\s+/g, ""), "base64").toString("utf8");
    case "quoted-printable":
      return decodeQuotedPrintable(body);
    default:
      return body;
  }
}

/** First text/plain part of a (possibly nested) MIME message. */
function textPart(raw: string): string | null {
  const { headers, body } = splitHeaders(raw);
  const contentType = headers.get("content-type") ?? "text/plain";
  const boundary = /boundary="?([^";]+)"?/i.exec(contentType)?.[1];
  if (contentType.toLowerCase().startsWith("multipart/") && boundary) {
    for (const part of body.split(`--${boundary}`).slice(1)) {
      if (part.startsWith("--")) break;
      const found = textPart(part.replace(/^\n/, ""));
      if (found !== null) return found;
    }
    return null;
  }
  if (contentType.toLowerCase().startsWith("text/plain")) {
    return decodeBody(body, headers.get("content-transfer-encoding"));
  }
  return null;
}

function parse(file: string): ReceivedEmail {
  const raw = readFileSync(file, "utf8");
  const { headers } = splitHeaders(raw);
  return {
    to: headers.get("to") ?? "",
    subject: decodeEncodedWords(headers.get("subject") ?? ""),
    text: textPart(raw) ?? "",
    file,
  };
}

/** Wait for an e-mail to ``to`` whose text contains ``contains``. */
export async function waitForEmail(
  to: string,
  contains: string,
  { timeoutMs = 30_000, since = 0 }: { timeoutMs?: number; since?: number } = {},
): Promise<ReceivedEmail> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    let files: string[] = [];
    try {
      files = readdirSync(MAIL_DIR)
        .filter((name) => name.endsWith(".eml"))
        .map((name) => path.join(MAIL_DIR, name))
        .filter((file) => statSync(file).mtimeMs >= since)
        .sort()
        .reverse();
    } catch {
      files = [];
    }
    for (const file of files) {
      const email = parse(file);
      if (email.to.toLowerCase().includes(to.toLowerCase()) && email.text.includes(contains)) return email;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`E-posta gelmedi: ${to} (${contains})`);
}

/** Relative path + fragment of the one-time link in an e-mail body. */
export function oneTimeLink(email: ReceivedEmail, pathPrefix: string): string {
  const match = new RegExp(`https?://[^\\s]+${pathPrefix}[^\\s]*#token=[A-Za-z0-9_.~%-]+`).exec(email.text);
  if (!match) throw new Error(`Bağlantı bulunamadı: ${pathPrefix}`);
  const url = new URL(match[0]);
  return `${url.pathname}${url.search}${url.hash}`;
}
