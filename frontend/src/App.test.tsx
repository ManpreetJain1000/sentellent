import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("renders the MVP scope and retention language", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );

    expect(html).toContain("Phase 1 MVP");
    expect(html).toContain("authentication");
    expect(html).toContain("organization management");
    expect(html).toContain("Conversation data is retained for 30 days.");
    expect(html).toContain("Sign in");
  });
});
