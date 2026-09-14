import { createHmac } from "node:crypto";

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

function base32Decode(input: string): Buffer {
  const clean = input.replace(/[\s=]/g, "").toUpperCase();
  let bits = 0;
  let value = 0;
  const out: number[] = [];
  for (const char of clean) {
    const index = ALPHABET.indexOf(char);
    if (index === -1) throw new Error("Geçersiz base32 karakteri");
    value = (value << 5) | index;
    bits += 5;
    if (bits >= 8) {
      out.push((value >>> (bits - 8)) & 0xff);
      bits -= 8;
    }
  }
  return Buffer.from(out);
}

export function timeStep(now = Date.now()): number {
  return Math.floor(now / 1000 / 30);
}

/** RFC 6238 TOTP (SHA-1, 6 digits, 30 s) — same parameters as the API. */
export function totp(secret: string, step = timeStep()): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(step));
  const digest = createHmac("sha1", base32Decode(secret)).update(counter).digest();
  const offset = digest.readUInt8(digest.length - 1) & 0x0f;
  return ((digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).toString().padStart(6, "0");
}

/** Code for a time step after ``usedStep`` (the API rejects replayed steps). */
export async function freshTotp(secret: string, usedStep: number): Promise<{ code: string; step: number }> {
  while (timeStep() <= usedStep) {
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  const step = timeStep();
  return { code: totp(secret, step), step };
}
