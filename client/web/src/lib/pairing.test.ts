import { describe, expect, it } from "vitest";
import { formatPairingCode } from "./pairing";

describe("formatPairingCode", () => {
  it("uppercases and inserts a dash", () => {
    expect(formatPairingCode("abcd efgh")).toBe("ABCD-EFGH");
    expect(formatPairingCode("ab-cd-ef-gh")).toBe("ABCD-EFGH");
  });

  it("keeps a partial code while typing", () => {
    expect(formatPairingCode("ab")).toBe("AB");
    expect(formatPairingCode("abcde")).toBe("ABCD-E");
  });

  it("drops extra characters", () => {
    expect(formatPairingCode("ABCD-EFGH-XXXX")).toBe("ABCD-EFGH");
  });
});
