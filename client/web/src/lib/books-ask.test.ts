import { describe, expect, it } from "vitest";
import {
  hideBookSlug,
  runPromptForBook,
  slugsConsumedByRunPrompt,
  visibleSkillBooks,
} from "./books-ask";

const invoice = { slug: "invoice", name: "Invoice" };
const extra = { slug: "extra", name: "Extra" };

describe("skill composer chips", () => {
  it("consumes the chip whose run prompt was sent", () => {
    expect(slugsConsumedByRunPrompt("please run Invoice", [invoice, extra])).toEqual(["invoice"]);
    expect(slugsConsumedByRunPrompt("hello", [invoice])).toEqual([]);
  });

  it("hides a dismissed slug for that chat only", () => {
    const hidden = hideBookSlug({}, "bot-a", invoice.slug);
    expect(visibleSkillBooks([invoice, extra], hidden, "bot-a")).toEqual([extra]);
    expect(visibleSkillBooks([invoice, extra], hidden, "bot-b")).toEqual([invoice, extra]);
    expect(runPromptForBook(invoice.name)).toBe("please run Invoice");
  });
});
