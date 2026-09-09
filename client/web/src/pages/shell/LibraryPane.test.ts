import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { LibraryPane } from "./LibraryPane";

describe("LibraryPane", () => {
  it("groups reusable capabilities instead of scattering provider doors around chat", () => {
    const html = renderToStaticMarkup(
      createElement(LibraryPane, {
        botName: "Research desk",
        hasActiveBot: true,
        modelsReady: true,
        showRoutines: false,
        onOpenPlugins: vi.fn(),
        onOpenModels: vi.fn(),
        onOpenMemory: vi.fn(),
        onOpenRoutines: vi.fn(),
        onOpenSettings: vi.fn(),
        onClose: vi.fn(),
      }),
    );

    expect(html).toContain('data-testid="library-pane"');
    expect(html).toContain("Connections");
    expect(html).toContain("Models");
    expect(html).toContain("Appearance");
    expect(html).toContain(">System<");
    expect(html).toContain(">Light<");
    expect(html).toContain(">Dark<");
    expect(html).toContain('role="radiogroup"');
    expect(html).toContain('aria-checked="true"');
    expect(html).toContain("Memory");
    expect(html).toContain("Bot profile &amp; access");
    expect(html).not.toContain(">Routines<");
    expect(html).toContain('data-testid="library-open-settings"');
    expect(html).toContain("Research desk");
  });

  it("keeps routines reachable from the phone More panel", () => {
    const html = renderToStaticMarkup(
      createElement(LibraryPane, {
        botName: "Research desk",
        hasActiveBot: true,
        modelsReady: true,
        showRoutines: true,
        onOpenPlugins: vi.fn(),
        onOpenModels: vi.fn(),
        onOpenMemory: vi.fn(),
        onOpenRoutines: vi.fn(),
        onOpenSettings: vi.fn(),
        onClose: vi.fn(),
      }),
    );

    expect(html).toContain(">Routines<");
  });
});
