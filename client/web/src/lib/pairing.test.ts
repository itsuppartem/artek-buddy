import { describe, expect, it } from "vitest";
import { formatPairingCode } from "./pairing";

describe("formatPairingCode", () => {
  it("uppercases and strips junk", () => {
    expect(formatPairingCode("ab-cd")).toBe("ABCD");
  });

  it("inserts a dash after four characters", () => {
    expect(formatPairingCode("abcdefgh")).toBe("ABCD-EFGH");
  });

  it("keeps at most eight letters or digits", () => {
    expect(formatPairingCode("abcdefghijkl")).toBe("ABCD-EFGH");
  });
});
