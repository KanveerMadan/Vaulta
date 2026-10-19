# Stage 2: balance reconciliation and real-file testing

Real files: the owner's own Kotak Mahindra Bank PDF statement and Google Pay PDF statement, 1 Jul – 30 Sep 2026,
from `local-statements/` (git-ignored, never committed). Everything ran locally against the test database with a
throwaway test user; only counts were printed. Nothing from these files is in this report, the tests or the fixtures.

## Results

| Check | Kotak PDF | Google Pay PDF |
|---|---|---|
| Recognised | after fix 1 (was: column mapping) | yes |
| Rows read | 218 of 218 (156 debits, 62 credits) | 159 of 159 (one per "UPI Transaction ID") |
| Rows missing date / amount / description | 0 | 0 |
| Balance check | pass (after fix 2: PDFs weren't checked) | n/a (no running balance) |
| Rows the server rejected | 0 (after the browser's privacy step) | 0 |
| Re-import the same file | 218 merged, 0 new | 159 merged, 0 new |

Both together: 250 transactions. 127 Google Pay payments merged into their Kotak rows by UPI transaction ID (after
fix 3), 8 self-transfers paired as transfers on both sides (after fix 4), and 24 Google Pay payments made from
another account stayed separate, as they should.

Categories with no corrections yet (model threshold 0.65): 106 of 377 rows filed automatically (80 known
merchant, 26 model). Most of the rest are payments to and from people, which no merchant step or model can file;
the People feature and corrections cover them. This is the "weak known-merchant step" decision already open.

## Fixes found by the real files

1. **Kotak's PDF statement wasn't recognised.** Its columns ("#", "Date", "Description", "Chq/Ref. No.",
   "Withdrawal (Dr.)", "Deposit (Cr.)", "Balance") differ from Kotak's CSV. Added the layout (`banks.js` `kotakPdf`).
2. **PDF bank statements had no balance check**, only CSV/Excel ones. Added (`index.js`).
3. **Google Pay payments didn't merge with their Kotak rows by UTR.** Kotak's reference column holds its own
   number; the UTR is in the narration, and the privacy step removed it there as a possible account number. A UPI
   narration's UTR is now the row's reference (`pii.js`). Before: 113 merged by date and amount, 22 duplicates.
4. **Google Pay self-transfers were read as payments.** "Self transfer to" also matched the "transfer to" rule
   (`upi.js`), so the Kotak credit leg counted as income and the other leg as spending.

Tests: `balance.test.js` (Kotak PDF layout, made-up rows), `parsers.test.js` (self-transfer in the pdf.js layout).
