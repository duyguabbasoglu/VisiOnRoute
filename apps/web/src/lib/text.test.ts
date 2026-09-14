import { describe, expect, it } from "vitest";
import { can } from "./permissions";
import { SLUG_PATTERN, passwordProblems, slugify } from "./text";

describe("slugify", () => {
  it("transliterates Turkish characters into a valid slug", () => {
    const slug = slugify("Çağrı Işık Öztürk Şüheda Lojistik A.Ş.");
    expect(slug).toBe("cagri-isik-ozturk-suheda-lojistik-a-s");
    expect(SLUG_PATTERN.test(slug)).toBe(true);
  });
});

describe("passwordProblems", () => {
  it("mirrors the backend policy", () => {
    expect(passwordProblems("kisa")).not.toHaveLength(0);
    expect(passwordProblems("sadeceharflerdenoluşan")).not.toHaveLength(0);
    expect(passwordProblems("GuvenliParola42!")).toHaveLength(0);
  });
});

describe("can", () => {
  const base = {
    id: "u",
    email: "e",
    full_name: "n",
    organization_id: "o",
    organization_name: "O",
    role_label: null,
    is_platform_admin: false,
    email_verified: true,
    mfa_enabled: false,
    mfa_required: false,
  };
  it("hides management controls from read-only roles", () => {
    expect(can({ ...base, role: "analyst" }, "org.update")).toBe(false);
    expect(can({ ...base, role: "analyst" }, "reports.read")).toBe(true);
    expect(can({ ...base, role: "owner" }, "subscription.manage")).toBe(true);
    expect(can({ ...base, role: "admin" }, "subscription.manage")).toBe(false);
    expect(can(null, "org.read")).toBe(false);
  });
});
