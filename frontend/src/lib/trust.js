// The privacy claims on the landing and /security pages. Each one is true of the code today;
// change this list (and the "how it works") only together with the code that makes it true.
export const TRUST = [
  {
    claim: "Statements are processed on your device and never uploaded.",
    how: "CSV, Excel, PDF and photo statements are read in your browser (the PDF reader and the text recognition run on your device). Vaulta shows you the rows it found, and only the rows you confirm are sent — as dates, descriptions and amounts, never the file.",
  },
  {
    claim: "Account numbers, balances and passwords are never stored.",
    how: "The importer skips the statement header, the account number and the running balance column, and removes account and card numbers from descriptions before anything is sent. A statement's PDF password is used on your device to open the file and is never sent. Sign-in is handled by Google's Firebase, so Vaulta's servers never see your login password either.",
  },
  {
    claim: "Raw alert emails are never stored.",
    how: "Forwarded bank alerts are read in memory on arrival. Vaulta keeps the transaction it found (date, description with personal details masked, amount) and a note of which bank sent it and when — or, for Gmail's forwarding confirmation, just its link and code. The email itself and the rest of its text are discarded, and attachments are dropped before the email reaches Vaulta.",
  },
  {
    claim: "The AI never sees bank narrations or UPI IDs.",
    how: "When AI chat is on, the assistant gets merchant names, categories, amounts and dates from Vaulta's own calculations. Raw statement descriptions, references, UPI IDs and your notes are removed before anything reaches it. You can turn AI chat off in Settings.",
  },
  {
    claim: "Delete everything, anytime.",
    how: "Settings → Delete everything removes your account and every transaction, budget, goal, report, alert and chat message from Vaulta's database at once.",
  },
];
