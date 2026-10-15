# Vaulta inbound email worker

Receives bank alert emails users forward to their personal address
(`<token>@in.<INBOUND_DOMAIN>`), and passes each one to the Vaulta API.

```
Bank → user's Gmail → (filter: forward) → <token>@in.yourdomain.in
     → Cloudflare Email Routing (catch-all) → this worker
     → POST {API_URL}/internal/inbound-email   (X-Internal-Secret)
```

The worker parses the message in memory, **drops attachments**, keeps the
payload under **256 KB**, and stores nothing. The API also processes it in
memory: it keeps only metadata (bank, outcome, time) and, for genuine alerts,
the normalized PII-stripped transaction row. Raw email is never persisted.

## Setup

1. **Domain.** In Cloudflare, the zone for `yourdomain.in`. Use a dedicated
   subdomain for inbound mail: `in.yourdomain.in`.
2. **Email Routing.** Zone → Email → Email Routing → enable it for
   `in.yourdomain.in` (Cloudflare adds the MX and SPF records).
3. **Deploy the worker.**
   ```sh
   cd infra/email-worker
   npm install
   # set API_URL in wrangler.toml to the API's public URL
   npx wrangler secret put INTERNAL_SECRET     # same value as the API's INTERNAL_SECRET
   npx wrangler deploy
   ```
4. **Catch-all rule.** Email Routing → Routing rules → Catch-all address →
   action "Send to a Worker" → `vaulta-inbound-email`.
5. **API.** Set `INBOUND_DOMAIN=yourdomain.in` on the API service (the
   address host becomes `in.yourdomain.in`).

## Checks

- `npm test` runs the payload tests (attachments dropped, size cap).
- Send a test email to a user's address; the Connect page shows the result.
  A message from a non-bank sender, or one failing DKIM/SPF, is discarded and
  only counted.

## Gmail forwarding

Gmail asks the target address to confirm forwarding by email. The API
recognizes that message (from `forwarding-noreply@google.com`, DKIM-signed by
google.com) and shows the confirmation link/code on the Connect page. Vaulta
never clicks it: the user does.

## Unverified

- The `Authentication-Results` header Cloudflare passes to workers is used
  for the DKIM/SPF check (with `ARC-Authentication-Results` as a fallback).
  Confirm on a real forwarded alert that it carries `dkim=pass header.d=<bank
  domain>`; Gmail auto-forwarding keeps the bank's DKIM signature valid but
  SPF will show Google, so DKIM is what normally passes.
