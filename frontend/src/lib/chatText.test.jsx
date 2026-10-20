// Chat replies: the model's **bold** shows as bold, never as asterisks.
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { plain, withBold } from "../lib/chatText.jsx";

describe("chat reply text", () => {
  it("turns **x** into bold and drops the asterisks", () => {
    const html = renderToStaticMarkup(<p>{withBold("You've spent **₹6,739** on food (**₹4,069** dining).")}</p>);
    expect(html).toContain("<strong");
    expect(html).toContain("₹6,739</strong>");
    expect(html).not.toContain("**");
  });
  it("leaves a half-arrived ** alone and reads plainly to screen readers", () => {
    expect(renderToStaticMarkup(<p>{withBold("spent **₹6,7")}</p>)).toBe("<p>spent **₹6,7</p>");
    expect(plain("a **b** c")).toBe("a b c");
  });
});
