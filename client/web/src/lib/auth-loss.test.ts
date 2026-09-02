import { describe, expect, it } from "vitest";
import { ApiError } from "../api";
import { healthOkClearsError, workspaceEventsAuthLoss } from "./auth-loss";

describe("workspaceEventsAuthLoss", () => {
  it("surfaces re-pair on 401 and 403", () => {
    expect(workspaceEventsAuthLoss(new ApiError("invalid token", 401))).toBe("repair");
    expect(workspaceEventsAuthLoss(new ApiError("forbidden", 403))).toBe("repair");
  });

  it("retries a dropped stream instead of a quiet paired window", () => {
    expect(workspaceEventsAuthLoss(new ApiError("Live updates stopped.", 502, true))).toBe("retry");
  });
});

describe("healthOkClearsError", () => {
  it("does not treat public /health as proof the device token is valid", () => {
    expect(healthOkClearsError("auth")).toBe(false);
    expect(healthOkClearsError("action")).toBe(false);
    expect(healthOkClearsError("host")).toBe(true);
    expect(healthOkClearsError(null)).toBe(false);
  });
});
