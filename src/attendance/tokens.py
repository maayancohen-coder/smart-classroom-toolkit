"""Rotating QR tokens (TOTP-like): HMAC(secret, session_id | time slot)."""
import hashlib
import hmac
import secrets
import time

from .models import TokenVerdict

SIGNATURE_LENGTH = 16  # hex chars kept from the HMAC (64 bits) - short enough for a dense-free QR


class TokenService:
    def __init__(self, period_seconds: int, grace_periods: int):
        self.period = period_seconds
        self.grace = grace_periods

    @staticmethod
    def new_secret() -> bytes:
        return secrets.token_bytes(32)

    def slot_at(self, now: float) -> int:
        return int(now // self.period)

    def sign(self, secret: bytes, session_id: str, slot: int) -> str:
        message = f"{session_id}|{slot}".encode()
        return hmac.new(secret, message, hashlib.sha256).hexdigest()[:SIGNATURE_LENGTH]

    def current(self, secret: bytes, session_id: str, now: float | None = None) -> tuple[int, str, float]:
        """Returns (slot, signature, seconds until the next rotation)."""
        now = time.time() if now is None else now
        slot = self.slot_at(now)
        expires_in = (slot + 1) * self.period - now
        return slot, self.sign(secret, session_id, slot), expires_in

    def verify(self, secret: bytes, session_id: str, slot: int, signature: str,
               now: float | None = None) -> TokenVerdict:
        now = time.time() if now is None else now
        expected = self.sign(secret, session_id, slot)
        # Constant-time compare: no timing side channel on the signature.
        if not hmac.compare_digest(expected, signature or ""):
            return TokenVerdict(False, reason="invalid signature")
        current_slot = self.slot_at(now)
        if slot > current_slot:
            return TokenVerdict(False, reason="token from the future")
        if current_slot - slot > self.grace:
            return TokenVerdict(False, age_seconds=now - slot * self.period, reason="expired token")
        return TokenVerdict(True, age_seconds=now - slot * self.period)
