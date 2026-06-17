import { describe, expect, it } from "vitest";

import { buildAppShell } from "./app-shell";

describe("buildAppShell", () => {
  it("describes the MVP scope and retention policy", () => {
    const shell = buildAppShell();

    expect(shell.title).toBe("Sentellent");
    expect(shell.scopeHighlights).toContain("authentication");
    expect(shell.scopeHighlights).toContain("organization management");
    expect(shell.scopeHighlights).toContain("chat workflows");
    expect(shell.scopeHighlights).toContain("task tracking");
    expect(shell.retentionPolicyDays).toBe(30);
  });
});
