// Cloudflare Email Worker: catch-all for in.<INBOUND_DOMAIN>.
// Parses the message in memory, drops attachments, and POSTs
// {to, from, subject, text, html, auth_results} to Vaulta's
// /internal/inbound-email. Nothing is stored or forwarded anywhere else.
import PostalMime from "postal-mime";
import { buildPayload, forInboundHost, MAX_BYTES } from "./payload.js";
import { deliver } from "./deliver.js";

export default {
  async email(message, env) {
    if (!forInboundHost(message.to, env.INBOUND_HOST)) {
      message.setReject("No such address");
      return;
    }
    // Bank alerts are small; anything far bigger isn't one (and isn't read).
    if (message.rawSize > MAX_BYTES * 4) {
      message.setReject("Message too large");
      return;
    }
    const parsed = await PostalMime.parse(message.raw);   // attachments are parsed but never used
    const payload = buildPayload({
      to: message.to,
      from: message.headers.get("from") || message.from,
      subject: parsed.subject,
      text: parsed.text,
      html: parsed.html,
      // Cloudflare's own SPF/DKIM/DMARC verdict; ARC header as a fallback
      authResults: message.headers.get("authentication-results") || message.headers.get("arc-authentication-results"),
    });
    if (!payload) return;
    await deliver(payload, env);   // waits out a sleeping API; throws (temporary failure) if it stays down
  },
};
