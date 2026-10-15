// Same names as CATEGORIES in backend/app/schemas/transaction.py
export const CATEGORIES = [
  "Food & Dining", "Groceries", "Transport", "Shopping", "Utilities", "Rent & Housing",
  "Health", "Entertainment", "Travel", "Education", "Software & Cloud", "Finance",
  "Insurance", "Investments", "Taxes & Government", "Sent to People", "Received from People",
  "Transfers", "Cash", "Misc cash", "Other",
];

// Same rules as KIND_DIRECTIONS in backend/app/models/transaction.py
export const KINDS = {
  spend: { label: "Spending", directions: ["debit"] },
  income: { label: "Income", directions: ["credit"] },
  transfer: { label: "Own-account transfer", directions: ["debit", "credit"] },
  refund: { label: "Refund", directions: ["credit"] },
  reversal: { label: "Failed / reversed", directions: ["debit", "credit"] },
  lent: { label: "Lent", directions: ["debit"] },
  borrowed: { label: "Borrowed", directions: ["credit"] },
  repayment: { label: "Repayment", directions: ["debit", "credit"] },
};

export const kindsFor = (direction) => Object.entries(KINDS).filter(([, k]) => k.directions.includes(direction));
