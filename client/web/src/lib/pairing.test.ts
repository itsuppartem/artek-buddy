import { describe, expect, it } from "vitest";
import { formatPairingCode, PAIRING_BODY, PAIRING_HOST_COMMAND } from "./pairing";

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

describe("pairing copy", () => {
  it("tells the owner where the code is and what Pair does", () => {
    expect(PAIRING_BODY.toLowerCase()).not.toContain("token");
    expect(PAIRING_BODY.toLowerCase()).not.toContain("mint");
    expect(PAIRING_BODY).toContain("pairing code");
    expect(PAIRING_BODY).toContain("Pair");
  });

  it("uses the README Compose exec, not a bare module", () => {
    expect(PAIRING_HOST_COMMAND).toBe("docker exec artek-buddy python -m artek_buddy pair");
  });
});
