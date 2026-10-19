#!/usr/bin/env bash
# Secret and personal-data check over the FULL history of every rebuild/phase* branch (or the refs given).
# Run before every push:   scripts/secret-check.sh            (exit 0 = clean, 1 = findings)
#                          scripts/secret-check.sh main        (other refs)
#
# Two independent checks, because gitleaks alone missed a Neon connection string in 2026-10:
#   1. gitleaks over the commits
#   2. every version of every file ever committed on those refs, searched for connection strings with
#      passwords, private keys, API tokens, Indian ID/card numbers, real-looking email addresses and
#      files that shouldn't be in git (.env, .eml, statements outside fixtures/)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

REFS=("$@")
if [ ${#REFS[@]} -eq 0 ]; then
  while IFS= read -r ref; do REFS+=("$ref"); done < <(git for-each-ref --format='%(refname:short)' 'refs/heads/rebuild/phase*')
fi
[ ${#REFS[@]} -gt 0 ] || { echo "no refs to scan"; exit 1; }
echo "Scanning: ${REFS[*]}"

# Already-public, rotated secrets. Listed by blob id so the secret itself never appears here.
#   5417a999… alembic.ini from 34e5052 (2026-06-14): Neon password, rotated 2026-10-16.
KNOWN_BLOBS="5417a9999ee01a3b602f5273c3052837d5d61da6"

status=0
command -v gitleaks >/dev/null || { echo "gitleaks is not installed (brew install gitleaks)"; exit 1; }

echo "== 1/2 gitleaks"
if ! gitleaks git --no-banner --redact --log-opts="${REFS[*]}" . ; then
  status=1
fi

echo "== 2/2 full-history file search"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
git rev-list --objects "${REFS[@]}" | git cat-file --batch-check='%(objecttype) %(objectname) %(rest)' |
  awk '$1 == "blob" { print $2 " " substr($0, index($0, $3)) }' > "$TMP/blobs"

if ! python3 - "$TMP/blobs" "$KNOWN_BLOBS" <<'PY'
import re, subprocess, sys

blobs_file, known = sys.argv[1], set(sys.argv[2].split())
SECRET = [
    # a password that is only a <placeholder> or a $VARIABLE (docs and runbooks) is not a credential
    ("connection string with a password", re.compile(rb"\b(postgres(ql)?|mysql|mongodb(\+srv)?|redis)://[^:\s/@]+:(?![<$])[^@\s/]{4,}@")),
    ("Neon password", re.compile(rb"\bnpg_[A-Za-z0-9]{8,}")),
    ("private key", re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Google API key", re.compile(rb"AIza[0-9A-Za-z_-]{35}")),
    ("Razorpay key", re.compile(rb"rzp_(live|test)_[A-Za-z0-9]{8,}")),
    ("Resend key", re.compile(rb"\bre_[A-Za-z0-9]{20,}")),
    ("Groq key", re.compile(rb"\bgsk_[A-Za-z0-9]{20,}")),
    ("Telegram bot token", re.compile(rb"\b[0-9]{8,10}:AA[0-9A-Za-z_-]{30,}")),
    ("Fernet/secret assignment", re.compile(rb"^(SECRET_KEY|ENCRYPTION_KEY|INTERNAL_SECRET|RAZORPAY_KEY_SECRET|RESEND_API_KEY|GROQ_API_KEY|TELEGRAM_BOT_TOKEN)=\S{8,}", re.M)),
    ("PAN", re.compile(rb"\b[A-Z]{3}[PCHABGJLFT][A-Z][0-9]{4}[A-Z]\b")),
    ("Aadhaar", re.compile(rb"\b[2-9][0-9]{3} [0-9]{4} [0-9]{4}\b")),
]
# made-up addresses used by tests and fixtures (incl. reserved TLDs: .test .example .invalid .localhost),
# and the bank/UPI senders the app trusts
SAFE_EMAIL = re.compile(rb"@(([a-z0-9-]+\.)*(example\.(com|org|in)|test\.local|[a-z0-9-]+\.(test|example|invalid|localhost)|yourdomain\.in|anthropic\.com|"
                        rb"[a-z0-9-]+\.iam\.gserviceaccount\.com|vaulta\.in|[a-z0-9-]+\.firebaseapp\.com|gmail\.com|evil\.example|elsewhere\.example|shop\.example)|"
                        rb"([a-z0-9-]+\.)*(hdfcbank|icicibank|sbi|sbicard|axisbank|kotak|yesbank|indusind|idfcfirstbank|bankofbaroda|pnb|"
                        rb"canarabank|unionbankofindia|federalbank|aubank|rblbank|americanexpress|aexp|paytm|paytmbank|phonepe|google)\.(com|net|in|co\.in|bank\.in))$", re.I)
EMAIL = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# gmail.com appears only as made-up test senders; flag the repo owner's address if it ever shows up
OWNER = re.compile(rb"kanveer" + rb"madan@", re.I)   # split so this file doesn't match itself
BAD_PATH = re.compile(r"(^|/)\.env(\.|$)(?!(e2e|example)$)|\.(eml|msg|p12|pfx|pem|key)$|(^|/)local-statements/|service[-_]?account.*\.json$", re.I)
DATA_FILE = re.compile(r"\.(pdf|csv|xlsx?|png|jpe?g|webp|heic)$", re.I)
# allowed binary data: synthetic statement fixtures, app icons, and the browser tests' visual
# snapshots (screenshots of seeded synthetic accounts, frontend/e2e/visual.spec.js and devices.spec.js), and the
# merchant model's evaluation charts (aggregate metrics on synthetic data, written by ml/train.py), and the made-up
# statement the "try it" page opens (frontend/public/samples/)
DATA_OK = re.compile(r"^(fixtures/statements/|frontend/public/icon-|frontend/src/assets/|frontend/e2e/(visual|devices)\.spec\.js-snapshots/|docs/ml/[a-z0-9-]+\.png$|frontend/public/samples/[a-z0-9-]+\.csv$|frontend/public/og\.png$)")

findings = []
for line in open(blobs_file):
    sha, _, path = line.rstrip("\n").partition(" ")
    if path.endswith("package-lock.json"):
        continue
    if BAD_PATH.search(path):
        findings.append(f"{path}: file type that must not be committed")
    if DATA_FILE.search(path) and not DATA_OK.search(path):
        findings.append(f"{path}: data file outside fixtures/statements/")
    if sha in known:
        continue
    data = subprocess.run(["git", "cat-file", "blob", sha], capture_output=True).stdout
    for name, rx in SECRET:
        if rx.search(data):
            findings.append(f"{path} (blob {sha[:8]}): {name}")
    if OWNER.search(data):
        findings.append(f"{path} (blob {sha[:8]}): the owner's email address")
    # The loose email pattern isn't run on images: their bytes are compressed pixels, where it matches random bytes
    # and can't see text drawn in the picture anyway. The secret patterns above still run on them.
    is_image = data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff"
    for m in ([] if is_image else set(EMAIL.findall(data))):
        if not SAFE_EMAIL.search(m):
            findings.append(f"{path} (blob {sha[:8]}): email address ***@{m.decode(errors='replace').rpartition('@')[2]}")

for f in sorted(set(findings)):
    print("  FOUND", f)
print(f"  {sum(1 for _ in open(blobs_file))} file versions searched, {len(set(findings))} finding(s)")
sys.exit(1 if findings else 0)
PY
then
  status=1
fi

if [ $status -eq 0 ]; then echo "CLEAN"; else echo "FINDINGS: do not push"; fi
exit $status
