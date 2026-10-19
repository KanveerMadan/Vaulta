"""The shared, read-only demo account (seeded by services/demo.py)."""

DEMO_UID = "vaulta-demo"            # firebase_uid of the demo user; no Firebase account has this uid format


def is_demo(user) -> bool:
    return user is not None and user.firebase_uid == DEMO_UID
