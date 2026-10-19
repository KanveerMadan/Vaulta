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
    how: "The importer leaves out the statement header, the account number and the running balance, and removes account and card numbers from descriptions before anything is sent. The balances are only used on your device to check that the rows read add up to the statement's closing balance; the preview shows whether they do, never the figures. A statement's PDF password is used on your device to open the file and is never sent. Sign-in is handled by Google's Firebase, so Vaulta's servers never see your login password either.",
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
    how: "AI chat and the written summary at the top of each report use Groq (OpenAI's open-weight gpt-oss-120b model, run by Groq). For chat, Groq receives your question, the last few turns of the conversation and the figures Vaulta calculates to answer it: merchant names, categories, amounts and dates. For a report summary it receives that report's figures. Raw statement descriptions, references, UPI IDs, account details and your notes are removed before anything is sent, and Groq handles what it receives under its own terms. Turning AI chat off in Settings stops chat; report summaries are still written this way unless you turn the report off.",
    checked: "Tests record every request to the AI and check it for narrations, references, UPI IDs and notes.",
  },
  {
    id: "categories",
    claim: "Categories are worked out without sending your transactions to an AI.",
    how: "Vaulta files transactions with its own small model (character patterns and logistic regression), after your rules, your own past corrections of similar payments and the merchants it knows. For statements it runs in your browser; for forwarded alerts, manual entries and Telegram it runs on Vaulta's server. The model file is served by Vaulta itself. It was trained on synthetic transactions made from a catalogue of public merchant names, labelled by AI models on Groq, which received only those merchant names; no one's transactions were used. When it isn't sure enough, the transaction goes to your review queue instead of being guessed. \"Why is it filed here?\" on any transaction says why it has its category. Your corrections only ever change your own categories, unless you turn on \"Let my category corrections help improve Vaulta's categories\" in Settings: then the corrected descriptions (with personal details already masked) and the categories you chose may be used to retrain the model.",
    checked: "Tests check that the browser, the server and the training code give the same answers, that your corrections always win and apply only to you, that re-checking categories never changes what you corrected and can be undone, that only consenting users' corrections are exported, and that logs and the model's metrics contain no merchant names. The scripts that build the training data, and the labels the AI gave, are in the repository (ml/).",
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
    how: "Settings → Your data downloads everything Vaulta holds about you, decrypted, as a zip of JSON and CSV files. It's built when you ask and isn't kept. Settings → Delete everything (after you sign in again and type DELETE) removes every transaction, budget, goal, person, rule, report, alert, chat message and activity record, your encryption key, forwarding address and Telegram link from Vaulta's database at once, then deletes your sign-in itself and emails you a confirmation. If the sign-in can't be deleted at that moment, the deletion is recorded and finished within the hour, and the sign-in can't be used in the meantime. Settings → Activity lists sign-ins, exports, deletions, sign-in method changes and settings changes.",
    checked: "Tests check that the export holds everything, decrypted; that after deleting, no table has a row of the account left and the sign-in no longer exists; and that a failed sign-in deletion is finished by the hourly run.",
  },
  {
    id: "errors",
    claim: "Error reports never carry your financial data.",
    how: "When something breaks, Vaulta sends an error report to Sentry (EU region) so it can be fixed: the kind of error and where in the code it happened. Before it leaves your browser or Vaulta's server, the report loses request contents, cookies, headers, search terms, who you are, and from any text, emails, UPI IDs, amounts, long numbers and anything quoted (where transaction descriptions, merchants and names would appear). There is no session recording or performance tracing.",
    checked: "A test sends a real server error with a narration, a UPI ID, an email, amounts, a session token and a search term in every part of the request and finds none of them in what reaches Sentry; a unit test does the same for the web app's scrubber.",
  },
  {
    id: "bots",
    claim: "Bot checks only where bots do harm.",
    how: "Vaulta uses Google reCAPTCHA v3 when you start the demo, create your account, ask for a password reset, import transactions or use chat, and nowhere else: Google's script isn't loaded for someone just reading a page. When it runs, Google receives what reCAPTCHA uses to tell people from scripts (your IP address, browser details and how the page is being used) under Google's own privacy policy. Vaulta's server checks the result with Google. A low score never locks you out: it only slows down repeated attempts, and anything that saves data already needs a confirmed email address.",
    checked: "Tests check that a missing or forged token is refused when checks are on, that a token made for another action or another website is refused, that a low score is slowed down and not refused, that Vaulta keeps working if Google can't be reached, and which requests carry a token.",
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
