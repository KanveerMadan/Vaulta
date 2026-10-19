// reCAPTCHA (lib/recaptcha.js): which requests carry a token, and the 'signup' token stops once the account is known.
import { describe, expect, it } from "vitest";
import { actionFor } from "./recaptcha.js";

describe("recaptcha", () => {
  it("names an action for the routes bots would abuse, and nothing for the rest", () => {
    expect(actionFor("/auth/demo")).toBe("demo");
    expect(actionFor("/auth/password-reset-requested")).toBe("password_reset");
    expect(actionFor("/api/import/batch", { signedIn: true, accountKnown: true })).toBe("import");
    expect(actionFor("/api/chat", { signedIn: true, accountKnown: true })).toBe("chat");
    expect(actionFor("/api/transactions", { signedIn: true, accountKnown: true })).toBeNull();
    expect(actionFor("/api/transactions")).toBeNull();
  });
  it("sends a 'signup' token while a signed-in account may still be created, then stops", () => {
    expect(actionFor("/auth/me", { signedIn: true, accountKnown: false })).toBe("signup");
    expect(actionFor("/api/home", { signedIn: true, accountKnown: false })).toBe("signup");
    expect(actionFor("/auth/me", { signedIn: true, accountKnown: true })).toBeNull();
  });
});
