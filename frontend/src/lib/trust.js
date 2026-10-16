// The privacy and security claims on /security (and, where `landing` is set, the landing page). Each one is true of
// the code today and names the tests that check it; change this list only together with the code that makes it true.
// /security shows every claim with a link to its "how it works" section (id `how-<id>`); the landing page links to
// the claim (`claim-<n>`). src/lib/wording.test.js and e2e/public.spec.js check both.

export const SECURITY_CONTACT = import.meta.env.VITE_SECURITY_CONTACT || "";
export const PRIVACY_CONTACT = import.meta.env.VITE_PRIVACY_CONTACT || "";

export const TRUST = [
  {
    id: "on-device",
    landing: true,
    claim: "Statements are processed on your device and never uploaded.",
    how: "CSV, Excel, PDF and photo statements are read in your browser (the PDF reader and the text recognition run on your device). Vaulta shows you the rows it found, and only the rows you confirm are sent, as dates, descriptions and amounts, never the file.",
    checked: "Every browser test fails if any request uploads a file or carries a statement's contents.",
  },
  {
    id: "stripped",
    landing: true,
    claim: "Account numbers, balances and passwords are never stored.",
    how: "The importer skips the statement header, the account number and the running balance column, and removes account and card numbers from descriptions before anything is sent. A statement's PDF password is used on your device to open the file and is never sent. Sign-in is handled by Google's Firebase, so Vaulta's servers never see your login password either.",
    checked: "Unit tests of every statement parser and of the personal-data stripping; browser tests of the import preview.",
  },
  {
    id: "encrypted",
    landing: true,
    claim: "Your transactions, people, notes and chats are encrypted with a key that is yours alone.",
    how: "Descriptions, merchant names, notes, the people you pay, goal names, chat messages, report text and alert messages are encrypted in the database (AES-256-GCM) with a data key made for your account alone. That key is itself encrypted with a master key that is kept outside the database, so a copy of the database, a backup or stolen database credentials can't be read. Amounts, dates and categories stay readable so totals can be added up. Vaulta's server decrypts your data to show it to you, so this is encryption at rest, not end-to-end encryption.",
    checked: "A test copies every table of an account with months of activity and finds none of its merchant names, people, notes or chat text.",
  },
  {
    id: "isolated",
    landing: true,
    claim: "The database itself keeps every account's data apart.",
    how: "Vaulta's server connects to the database as a role that can only see rows belonging to the account it is working for (Postgres row-level security). Even a query that forgot to say whose data it wants would get nothing from anyone else's account.",
    checked: "Tests run queries without any account filter and get nothing of another account's; every route is also tried as a second user.",
  },
  {
    id: "alert-emails",
    landing: true,
    claim: "Raw alert emails are never stored.",
    how: "Forwarded bank alerts are read in memory on arrival. Vaulta keeps the transaction it found (date, description with personal details masked, amount) and a note of which bank sent it and when (or, for Gmail's forwarding confirmation, just its link and code). The email itself and the rest of its text are discarded, and attachments are dropped before the email reaches Vaulta.",
    checked: "A test forwards real-format alerts and then searches every table and the logs for their text.",
  },
  {
    id: "ai",
    landing: true,
    claim: "The AI never sees bank narrations or UPI IDs.",
    how: "AI chat and the written summary at the top of each report use Groq (the Llama 3.3 70B model). For chat, Groq receives your question, the last few turns of the conversation and the figures Vaulta calculates to answer it: merchant names, categories, amounts and dates. For a report summary it receives that report's figures. Raw statement descriptions, references, UPI IDs, account details and your notes are removed before anything is sent, and Groq handles what it receives under its own terms. Turning AI chat off in Settings stops chat; report summaries are still written this way unless you turn the report off.",
    checked: "Tests record every request to the AI and check it for narrations, references, UPI IDs and notes.",
  },
  {
    id: "telegram",
    claim: "Telegram is optional, and what you send there passes through Telegram.",
    how: "If you link Telegram, the messages you send the bot and its replies (amounts, merchant names, summaries and any alerts you send there) travel through Telegram's servers like any other Telegram chat; chats with bots aren't end-to-end encrypted. Bill photos sent there are never read. Unlink in Settings or send /unlink, and that chat stops reaching your account.",
    checked: "Tests of linking, one-time link codes, unlinking and the bot's replies.",
  },
  {
    id: "your-data",
    landing: true,
    claim: "Export or delete everything, anytime.",
    how: "Settings → Your data downloads everything Vaulta holds about you, decrypted, as a zip of JSON and CSV files. It's built when you ask and isn't kept. Settings → Delete everything removes your account and every transaction, budget, goal, report, alert, chat message and activity record from Vaulta's database at once. Settings → Activity lists sign-ins, exports, deletions, Telegram links and settings changes.",
    checked: "Tests check that the export holds everything, decrypted, and that after deleting, no table has a single row of the account left.",
  },
  {
    id: "checks",
    claim: "Every change is tested and security-scanned.",
    how: "Each change to Vaulta's code runs the full test suite, including the encryption and isolation checks above, plus automated security checks: a search of the code's entire history for leaked secrets, known-vulnerability audits of every dependency (pip-audit, npm audit), static analysis (Bandit, Semgrep) and an OWASP ZAP scan of the running app and API.",
    checked: "The continuous-integration workflow in the repository (.github/workflows/ci.yml).",
  },
  {
    id: "report",
    claim: "Found a security problem? Tell us.",
    how: "Write to the security contact below. It's also published at /.well-known/security.txt, the standard place security researchers look.",
    checked: "The address comes from the deployment's configuration, and a production build fails without it.",
  },
];

// The claims the landing page lists (each links to /security#claim-<n>, its position in TRUST)
export const LANDING_CLAIMS = TRUST.map((t, i) => ({ ...t, n: i + 1 })).filter((t) => t.landing);
