// Quick-add parser: "150 auto cash", "2400 groceries dmart yesterday".
// Plain keyword rules, run in the browser. The server re-normalizes the
// merchant; this only pre-fills the confirm chip.

const KEYWORDS = {
  "Transport": ["auto", "rickshaw", "cab", "taxi", "uber", "ola", "rapido", "metro", "bus", "train", "petrol", "diesel", "fuel", "parking", "toll"],
  "Groceries": ["grocery", "groceries", "vegetables", "veggies", "fruits", "milk", "kirana", "dmart", "bigbasket", "blinkit", "zepto", "instamart"],
  "Food & Dining": ["food", "lunch", "dinner", "breakfast", "snacks", "chai", "tea", "coffee", "restaurant", "swiggy", "zomato", "pizza", "biryani"],
  "Shopping": ["shopping", "clothes", "shoes", "amazon", "flipkart", "myntra", "gift"],
  "Utilities": ["electricity", "water", "gas", "wifi", "internet", "broadband", "recharge", "mobile", "bill"],
  "Rent & Housing": ["rent", "maintenance", "society", "maid", "plumber", "electrician"],
  "Health": ["medicine", "medicines", "pharmacy", "doctor", "hospital", "clinic", "chemist"],
  "Entertainment": ["movie", "movies", "netflix", "spotify", "concert", "game"],
  "Travel": ["flight", "hotel", "trip", "irctc", "holiday"],
  "Education": ["books", "course", "tuition", "fees", "school", "college"],
};

// Words that say what kind of spend it was rather than where ("dmart" names a merchant, "groceries" doesn't)
const GENERIC = new Set([
  "grocery", "groceries", "vegetables", "veggies", "fruits", "milk", "food", "lunch", "dinner", "breakfast",
  "snacks", "shopping", "clothes", "shoes", "gift", "electricity", "water", "gas", "wifi", "internet",
  "broadband", "recharge", "mobile", "bill", "rent", "maintenance", "medicine", "medicines", "doctor",
  "movie", "movies", "flight", "hotel", "trip", "holiday", "books", "course", "tuition", "fees",
  "petrol", "diesel", "fuel", "parking", "toll",
]);

const PAYMENT_WORDS = { cash: "cash", upi: "online", card: "online", online: "online", gpay: "online", phonepe: "online", paytm: "online", netbanking: "online" };
const INCOME_WORDS = new Set(["received", "got", "salary", "income", "refund", "credited"]);
const FILLER = new Set(["for", "on", "at", "to", "from", "paid", "spent", "rs", "inr", "via", "by", "the", "a"]);
const WEEKDAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];
const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const daysAgo = (today, n) => new Date(today.getFullYear(), today.getMonth(), today.getDate() - n);
const titleCase = (s) => s.replace(/\b\w/g, (c) => c.toUpperCase());

function dayMonth(day, month, today) {
  const d = new Date(today.getFullYear(), month, day);
  if (d.getMonth() !== month) return null;
  return d > today ? new Date(today.getFullYear() - 1, month, day) : d;
}

/**
 * Returns {amount, merchant, category, date, payment_method, direction} or
 * null when no amount is found. amount is a decimal string.
 */
export function parseQuickAdd(text, today = new Date()) {
  let rest = ` ${text.toLowerCase().trim()} `;
  let date = today;

  // dates first, so "12/3" isn't read as an amount
  const take = (re, fn) => { rest = rest.replace(re, (...m) => { const d = fn(...m); if (d) date = d; return " "; }); };
  take(/\bday before yesterday\b/, () => daysAgo(today, 2));
  take(/\byesterday\b/, () => daysAgo(today, 1));
  take(/\btoday\b/, () => today);
  take(new RegExp(`\\b(?:last\\s+)?(${WEEKDAYS.join("|")})\\b`), (_, w) => daysAgo(today, ((today.getDay() - WEEKDAYS.indexOf(w)) + 7) % 7 || 7));
  take(/\b(\d{1,2})[/-](\d{1,2})\b(?![/-]?\d)/, (_, d, m) => dayMonth(Number(d), Number(m) - 1, today));
  take(new RegExp(`\\b(\\d{1,2})\\s*(${MONTHS.join("|")})[a-z]*\\b`), (_, d, m) => dayMonth(Number(d), MONTHS.indexOf(m), today));

  const amountMatch = /(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d{1,2})?)\s*(k)?\b/.exec(rest);
  if (!amountMatch) return null;
  let amount = Number(amountMatch[1].replace(/,/g, ""));
  if (amountMatch[2]) amount *= 1000;
  if (!(amount > 0)) return null;
  rest = rest.replace(amountMatch[0], " ");

  const words = rest.split(/\s+/).filter((w) => w && !FILLER.has(w));
  let payment_method = "cash";
  let direction = "debit";
  let category = null;
  const named = [];
  const generic = [];
  for (const w of words) {
    if (PAYMENT_WORDS[w]) { payment_method = PAYMENT_WORDS[w]; continue; }
    if (INCOME_WORDS.has(w)) direction = "credit";
    category = category || Object.keys(KEYWORDS).find((c) => KEYWORDS[c].includes(w)) || null;
    (GENERIC.has(w) || INCOME_WORDS.has(w) ? generic : named).push(w);
  }
  const merchant = titleCase((named.length ? named : generic).join(" ")) || "Cash spend";

  return {
    amount: Number.isInteger(amount) ? String(amount) : amount.toFixed(2),
    merchant,
    category,
    date: iso(date),
    payment_method,
    direction,
  };
}
