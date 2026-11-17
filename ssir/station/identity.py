"""Station Identity: offline sign-in and per-person signing (NFR-003, K9)."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, PublicFormat, load_pem_private_key,
)

from ssir.domain_rules import NotFound, Signature, Unauthenticated, User
from ssir.station.onboard_store import OnboardStore

# Decisions (Nov 16, 2026): signatures are Ed25519 (`cryptography` package).
# Each private key arrives from the identity system as PEM PKCS#8, encrypted
# under the person's sign-in secret; a public key is the 32 raw Ed25519 bytes.
_SIGN_IN_FAILED = "unknown user or wrong secret"


@dataclass(frozen=True)
class Session:
    session_id: str
    user: User
    started_at: datetime


class StationIdentity:
    def __init__(self, store: OnboardStore) -> None:
        self._store = store
        # Unlocked keys live only in memory, only while the session lasts (K9).
        self._sessions: dict[str, tuple[Session, Ed25519PrivateKey, str]] = {}
        self._lock = threading.Lock()

    def sign_in(self, user_id: str, secret: str, now: datetime) -> Session:
        try:
            with self._store.read() as tx:
                user = tx.get_user(user_id)
                blob = tx.get_encrypted_private_key(user_id)
        except NotFound:
            raise Unauthenticated([_SIGN_IN_FAILED]) from None
        try:
            key = load_pem_private_key(blob, password=secret.encode("utf-8"))
        except (ValueError, TypeError):
            raise Unauthenticated([_SIGN_IN_FAILED]) from None
        if not isinstance(key, Ed25519PrivateKey):
            raise Unauthenticated(["stored key is not an Ed25519 key"])
        public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        record = next((r for r in user.public_keys if r.public_key == public), None)
        if record is None:
            raise Unauthenticated(["signing key is not registered for this user"])
        if record.revoked_at is not None and record.revoked_at <= now:
            raise Unauthenticated(["signing key has been revoked"])
        session = Session(session_id=uuid4().hex, user=user, started_at=now)
        with self._lock:
            self._sessions[session.session_id] = (session, key, record.key_id)
        return session

    def sign_out(self, session: Session) -> None:
        with self._lock:
            if self._sessions.pop(session.session_id, None) is None:
                raise Unauthenticated(["session is not active"])

    def sign(self, session: Session, content: bytes) -> Signature:
        with self._lock:
            entry = self._sessions.get(session.session_id)
        if entry is None or entry[0].user.user_id != session.user.user_id:
            raise Unauthenticated(["session is not active"])
        _, key, key_id = entry
        return Signature(key_id=key_id, value=key.sign(content))
