// The statement the landing page takes apart. Made-up account, realistic shape.
export const HOLDER = { name: 'KAVYA RAO', account: '50100123456789', ifsc: 'HDFC0001234', bank: 'HDFC Bank', period: '1 Oct to 15 Oct' }

// raw: what the statement says. clean: what crosses to Vaulta. group: where it sorts to.
export const ROWS = [
  { date: '01 Oct', raw: 'NEFT CR-ACME CORP PAYROLL-50100123456789', clean: 'Acme Corp payroll', amount: 92000, flow: 'in', balance: '1,14,210.50', group: 0 },
  { date: '03 Oct', raw: 'UPI-RAHUL SHARMA-rahul.s@okicici-Rent', clean: 'Rahul Sharma · r***@okicici', amount: 25000, flow: 'out', balance: '89,210.50', group: 1, recurring: 'Monthly' },
  { date: '05 Oct', raw: 'POS 4321XXXXXX9876 SWIGGY BANGALORE', clean: 'Swiggy', amount: 420, flow: 'out', balance: '88,790.50', group: 2 },
  { date: '07 Oct', raw: 'UPI-BLINKIT-blinkit@hdfcbank-412300009911', clean: 'Blinkit', amount: 640, flow: 'out', balance: '88,150.50', group: 3 },
  { date: '08 Oct', raw: 'NETFLIX COM 4321XXXXXX9876', clean: 'Netflix', amount: 649, flow: 'out', balance: '87,501.50', group: 4, recurring: 'Monthly' },
  { date: '11 Oct', raw: 'UPI-PRIYA MEHTA-priya.m@okaxis-Dinner', clean: 'Priya Mehta · p***@okaxis', amount: 800, flow: 'out', balance: '86,701.50', group: 2 },
]

export const GROUPS = ['Income', 'Rent & Housing', 'Food & Dining', 'Groceries', 'Subscriptions']

// What the redaction pass removes, in the order it happens
export const REMOVED = [
  'Your name',
  'Account number and IFSC',
  'Running balance',
  'Card numbers in descriptions',
  'Personal UPI IDs (masked)',
]

export const CAPTIONS = [
  { title: 'Your statement opens on your phone.', body: 'The file is read right here, in the browser. It is never uploaded.' },
  { title: 'Personal details are removed first.', body: 'Your name, account number, balance and card numbers are stripped on the device.' },
  { title: 'Only clean rows leave.', body: 'Date, description, amount. You see every row before it is sent.' },
  { title: 'vaulta.in sorts them for you.', body: 'Categories, people, transfers and recurring payments, worked out automatically.' },
  { title: 'And tells you where the month is going.', body: 'Safe to spend today, budgets, and a forecast for the month.' },
]
