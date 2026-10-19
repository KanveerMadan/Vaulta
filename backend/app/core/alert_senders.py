"""
Who may send transaction alerts. The one list used for:
  - sender trust on inbound email (services/email_alerts.py): the From
    domain must be one of `domains` (or a subdomain), or the exact address
    must be in `exact` — and DKIM/SPF must pass for it
  - the Gmail filter instructions on the Connect page (`senders`)

UNVERIFIED: addresses and domains are from public knowledge of Indian bank
alert senders; banks also move to *.bank.in domains (RBI, 2025). Check each
against a real alert and adjust here — nothing else needs to change.
"""

from __future__ import annotations

from typing import Optional

BANKS: list[dict] = [
    {"key": "hdfc", "name": "HDFC Bank", "domains": ["hdfcbank.net", "hdfcbank.com", "hdfc.bank.in", "hdfcbank.bank.in"],
     "senders": ["alerts@hdfcbank.net", "alerts@hdfcbank.bank.in"]},
    {"key": "icici", "name": "ICICI Bank", "domains": ["icicibank.com", "icici.bank.in"],
     "senders": ["alerts@icicibank.com", "credit_cards@icicibank.com"]},
    {"key": "sbi", "name": "SBI", "domains": ["sbi.co.in", "sbi.bank.in"],
     "senders": ["donotreply.sbiatm@alerts.sbi.co.in", "cbssbi.cas@alerts.sbi.co.in"]},
    {"key": "axis", "name": "Axis Bank", "domains": ["axisbank.com", "axis.bank.in"],
     "senders": ["alerts@axisbank.com"]},
    {"key": "kotak", "name": "Kotak Mahindra Bank", "domains": ["kotak.com", "kotak.bank.in"],
     "senders": ["BankAlerts@kotak.com", "creditcardalerts@kotak.com"]},
    {"key": "sbicard", "name": "SBI Card", "domains": ["sbicard.com"], "senders": ["onlinesbicard@sbicard.com"]},
    {"key": "yes", "name": "Yes Bank", "domains": ["yesbank.in", "yes.bank.in"], "senders": ["alerts@yesbank.in"]},
    {"key": "indusind", "name": "IndusInd Bank", "domains": ["indusind.com", "indusind.bank.in"],
     "senders": ["transactionalert@indusind.com"]},
    {"key": "idfc", "name": "IDFC FIRST Bank", "domains": ["idfcfirstbank.com", "idfcfirst.bank.in"],
     "senders": ["transaction.alerts@idfcfirstbank.com"]},
    {"key": "bob", "name": "Bank of Baroda", "domains": ["bankofbaroda.com", "bankofbaroda.co.in", "bankofbaroda.bank.in"],
     "senders": ["alerts@bankofbaroda.com"]},
    {"key": "pnb", "name": "Punjab National Bank", "domains": ["pnb.co.in", "pnb.bank.in"], "senders": ["alerts@pnb.co.in"]},
    {"key": "canara", "name": "Canara Bank", "domains": ["canarabank.com", "canarabank.in", "canarabank.bank.in"],
     "senders": ["alerts@canarabank.com"]},
    {"key": "union", "name": "Union Bank of India", "domains": ["unionbankofindia.co.in", "unionbankofindia.bank.in"],
     "senders": ["alerts@unionbankofindia.co.in"]},
    {"key": "federal", "name": "Federal Bank", "domains": ["federalbank.co.in", "federalbank.bank.in"],
     "senders": ["alerts@federalbank.co.in"]},
    {"key": "au", "name": "AU Small Finance Bank", "domains": ["aubank.in", "au.bank.in"], "senders": ["alerts@aubank.in"]},
    {"key": "rbl", "name": "RBL Bank", "domains": ["rblbank.com", "rbl.bank.in"], "senders": ["alerts@rblbank.com"]},
    {"key": "amex", "name": "American Express", "domains": ["americanexpress.com", "aexp.com"],
     "senders": ["americanexpress@welcome.americanexpress.com"]},
    {"key": "paytm", "name": "Paytm", "domains": ["paytm.com", "paytmbank.com"], "senders": ["no-reply@paytm.com"]},
    {"key": "phonepe", "name": "PhonePe", "domains": ["phonepe.com"], "senders": ["noreply@phonepe.com"]},
    # google.com sends far more than payments: only Google Pay's own address is trusted
    {"key": "gpay", "name": "Google Pay", "domains": [], "exact": ["googlepay-noreply@google.com"],
     "senders": ["googlepay-noreply@google.com"]},
]

# Gmail's forwarding-confirmation sender (never a source of transactions)
GMAIL_FORWARDING_SENDER = "forwarding-noreply@google.com"


def bank_for_sender(address: str) -> Optional[dict]:
    """The bank entry that may send from this address, or None."""
    address = (address or "").strip().lower()
    if "@" not in address:
        return None
    domain = address.rsplit("@", 1)[1]
    for bank in BANKS:
        if address in {a.lower() for a in bank.get("exact", [])}:
            return bank
        if any(domain == d or domain.endswith("." + d) for d in bank["domains"]):
            return bank
    return None


def sender_domain_ok(bank: dict, domain: str) -> bool:
    """Is `domain` (e.g. the DKIM d= or SPF mailfrom domain) one this bank sends from?"""
    domain = (domain or "").lower()
    allowed = list(bank["domains"]) + [a.rsplit("@", 1)[1].lower() for a in bank.get("exact", [])]
    return any(domain == d or domain.endswith("." + d) for d in allowed)
