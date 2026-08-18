import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, classifyError, request } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HTTP API unhappy paths", () => {
  it("turns a network failure into an actionable host message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(request("GET", "/health")).rejects.toMatchObject({
      name: "ApiError",
      retryable: true,
      message: "Could not reach the host. Check Tailscale or the host address, then try again.",
    });
  });

  it("keeps a pairing 403 as the host pairing message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: "invalid or expired pairing code" }), {
          status: 403,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(request("POST", "/local/pair", { pairingCode: "AAAA-BBBB" })).rejects.toMatchObject({
      status: 403,
      message: "invalid or expired pairing code",
    });
  });

  it("tells a revoked device to pair again instead of exposing a raw 403", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "invalid token" }), {
          status: 403,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(request("GET", "/v1/bots")).rejects.toMatchObject({
      status: 403,
      retryable: false,
      message: "This computer is no longer authorized. Pair it again to continue.",
    });
  });

  it("keeps successful responses camel-cased", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ agent_id: "agent-1" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(request<{ agentId: string }>("GET", "/health")).resolves.toEqual({
      agentId: "agent-1",
    });
  });

  it("classifies inbox-full as an action, not a host outage", () => {
    expect(
      classifyError(new ApiError("Too many messages are already queued.", 409)),
    ).toEqual({
      message: "Too many messages are already queued.",
      kind: "action",
    });
  });

  it("classifies a revoked token as auth", () => {
    expect(
      classifyError(new ApiError("This computer is no longer authorized. Pair it again to continue.", 403)),
    ).toMatchObject({ kind: "auth" });
  });

  it("classifies a dropped fetch as a host outage", () => {
    expect(
      classifyError(new ApiError("Could not reach the host. Check Tailscale or the host address, then try again.", undefined, true)),
    ).toMatchObject({ kind: "host" });
  });
});
