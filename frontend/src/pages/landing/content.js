// The landing page's copy. Every privacy or security line must be true of the code today (see /security);
// lines toned down from the brief for that reason are marked "softened:".

export const REPO_URL = 'https://github.com/KanveerMadan/Vaulta'
export const LINKEDIN_URL = 'https://www.linkedin.com/in/kanveermadan/'

// softened: "Open source" → the repository is public but has no licence yet, so it's "source-available"
export const CHIPS = ['Free', 'No bank login', 'No SMS access', 'Code on GitHub', 'Delete anytime']

export const PAIN = [
  { title: '₹200 here. ₹450 there.', body: "UPI made spending effortless. Tracking it didn't." },
  { title: 'Every month, around the 20th.', body: "The balance is lower than it should be, and you can't say why." },
  { title: 'Spreadsheets last a week.', body: 'Most budget apps want your bank password. Neither sticks.' },
]

export const STEPS = [
  { title: 'Drop your statement once.', body: 'Read on your phone. Never uploaded.', shot: 'cut-statement',
    alt: "vaulta.in's import preview: 12 transactions from HDFC Bank, balances check out, and the account number, name, IFSC and running balance struck out as removed on the device." },
  // softened: "within seconds" → forwarding plus a sleeping server can take a minute or two
  { title: 'Forward your bank alerts.', body: 'Every spend lands in vaulta.in on its own, a minute or two after your bank emails you.', shot: 'cut-alert',
    alt: 'A sample HDFC Bank UPI alert email and what vaulta.in made of it: Swiggy, Food & Dining, ₹450.' },
  { title: 'Just ask.', body: '“How much on food this month?” Real numbers, computed from your transactions, not guessed.', shot: 'chat',
    alt: 'vaulta.in chat answering "How much did I spend on food this month?" with ₹6,739: ₹4,069 on Food & Dining plus ₹2,670 on Groceries.' },
]

// softened: the other column says "Often…": a general claim about the market, never about one company
export const COMPARE = [
  ['Your bank login', 'Often asked for', 'Never'],
  ['Access to all your SMS', 'Often asked for', 'Never'],
  ['Account number and balance', 'Often stored', 'Stripped on your phone'],
  ['Your statement file', 'Often uploaded', 'Never leaves your device'],
  // softened: the server also gets a payment reference (UTR) and which account it came from
  ['What reaches the server', 'Often the whole statement', 'Date · cleaned description · amount'],
]

// each tile links to its claim on /security (by id in lib/trust.js), or to the code
export const TILES = [
  { icon: 'key', title: 'Your key, your data.', body: 'Everything you store is encrypted with a key made for your account alone.', claim: 'encrypted' },
  { icon: 'wall', title: 'Walled off.', body: "The database itself keeps every account's data apart.", claim: 'isolated' },
  { icon: 'mail', title: 'Emails read, then gone.', body: 'Bank alert emails are never stored.', claim: 'alert-emails' },
  // softened: "AI sees amounts, not identities" → it does see merchant names
  { icon: 'ai', title: 'AI sees totals, not your statement.', body: 'No bank narrations, no UPI IDs, no account details.', claim: 'ai' },
  { icon: 'leave', title: 'Leave anytime.', body: 'Export or delete everything, anytime.', claim: 'your-data' },
  // softened: "Fully open source" → public code, no licence yet
  { icon: 'code', title: "Don't trust us. Read the code.", body: 'Every line that runs vaulta.in is public on GitHub.', href: REPO_URL },
]

export const FEATURES = [
  { title: 'Know before you order.', body: 'Safe to spend today, so the Swiggy decision takes a second.', shot: 'cut-safe', inset: true,
    alt: 'vaulta.in home: safe to spend today ₹2,239, with ₹26,863 left this month for 12 days.' },
  { title: "Bills don't surprise you.", body: 'Rent, EMIs and subscriptions spotted automatically, and price rises flagged.', shot: 'cut-recurring',
    alt: 'Recurring payments: rent ₹25,000 every month, and Netflix ₹649 every month, flagged "Price up: ₹499 → ₹649".' },
  // softened: "Alerts the moment something needs you" → alerts go out as transactions arrive and from the hourly run
  { title: 'Your money, explained weekly.', body: 'A one-minute summary in your inbox, and an alert when something needs a look.', shot: 'email',
    alt: "vaulta.in's weekly report email: spent ₹2,699, top categories Groceries, Food & Dining and Transport." },
]

// The banks the importers know (frontend/src/import: banks.js, creditCard.js, upi.js) and the alert senders the API
// accepts (backend/app/core/alert_senders.py). content.test.js keeps these lists equal to the code.
export const STATEMENT_BANKS = ['HDFC Bank', 'ICICI Bank', 'SBI', 'Axis Bank', 'Kotak Mahindra Bank']
export const CARD_ISSUERS = ['HDFC Bank Credit Card', 'ICICI Bank Credit Card', 'SBI Card', 'Axis Bank Credit Card']
export const UPI_APPS = ['Google Pay', 'PhonePe', 'Paytm']
export const ALERT_SENDERS = ['HDFC Bank', 'ICICI Bank', 'SBI', 'Axis Bank', 'Kotak Mahindra Bank', 'SBI Card', 'Yes Bank',
  'IndusInd Bank', 'IDFC FIRST Bank', 'Bank of Baroda', 'Punjab National Bank', 'Canara Bank', 'Union Bank of India',
  'Federal Bank', 'AU Small Finance Bank', 'RBL Bank', 'American Express', 'Paytm', 'PhonePe', 'Google Pay']

const list = (xs) => `${xs.slice(0, -1).join(', ')} and ${xs.at(-1)}`
export const FAQ = [
  { q: 'Is it really free?', a: ['Yes.'] },
  // softened: "We barely have it" → Vaulta does keep your transactions (encrypted)
  { q: 'Do you sell my data?', a: ['No. And what we keep is encrypted with a key made for your account.'] },
  { q: 'Which banks work?', a: [
    `Bank statements (CSV, Excel or PDF) from ${list(STATEMENT_BANKS)}, read automatically.`,
    `Credit card statements (PDF) from ${list(CARD_ISSUERS.map((c) => c.replace(' Credit Card', '')))}.`,
    `Statements from ${list(UPI_APPS)}.`,
    "Any other bank's CSV, Excel or PDF works too: you match its columns once, and vaulta.in remembers. Photos of statements are read on your device.",
    // softened: "Alert emails work with most Indian banks" → these are the senders accepted; wording varies by bank
    `Forwarded alert emails are accepted from ${list(ALERT_SENDERS)}. Banks word their alerts differently, so any vaulta.in can't read lands in your review queue.`,
  ] },
  { q: 'Can you see my bank account?', a: ['No. No bank login, no SMS, no account numbers.'] },
  { q: 'What if vaulta.in shuts down?', a: ["Export everything anytime. We'll email you in advance whenever possible."] },
  { q: 'Who built this?', a: ["Built by Kanveer Madan, an AI/ML student in Delhi who got tired of asking “kahan gaye paise?” every month."], links: true },
]
