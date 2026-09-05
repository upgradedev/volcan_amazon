"""Domain: single-use, time-limited, content-bound approval grants.

An approval grant is the artifact a human presents to release a staged action.
It is not a password and not a bearer string that any non-empty value satisfies.
A grant is an HMAC-SHA256 signature over the tuple

    (action_id, payload_hash, expiry, nonce)

so a grant cannot be moved to a different action, cannot survive an edit to the
command it authorises (the payload hash changes), cannot be used after its
lease expires, and cannot be presented twice (the nonce is burned on use).

The signing secret is injected by the composition root. This module reads no
environment and imports no SDK, which keeps the domain layer framework-free.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from enum import Enum

GRANT_VERSION = "v1"


class GrantRefusal(str, Enum):
    """Why a grant was refused. Every value is a real, reachable code path."""

    MALFORMED = "MALFORMED"
    BAD_SIGNATURE = "BAD_SIGNATURE"
    WRONG_ACTION = "WRONG_ACTION"
    CONTENT_MISMATCH = "CONTENT_MISMATCH"
    EXPIRED = "EXPIRED"
    REPLAYED = "REPLAYED"


@dataclass(frozen=True)
class GrantVerdict:
    accepted: bool
    refusal: GrantRefusal | None = None
    detail: str = ""

    @property
    def spoken_reason(self) -> str:
        if self.accepted:
            return "Authorization grant accepted."
        reasons = {
            GrantRefusal.MALFORMED: "That authorization grant is not readable.",
            GrantRefusal.BAD_SIGNATURE: "That authorization grant failed its signature check.",
            GrantRefusal.WRONG_ACTION: "That authorization grant belongs to a different action.",
            GrantRefusal.CONTENT_MISMATCH: "The command changed after the grant was issued.",
            GrantRefusal.EXPIRED: "That authorization grant has expired.",
            GrantRefusal.REPLAYED: "That authorization grant was already used once.",
        }
        return reasons.get(self.refusal, "Authorization refused.")


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


class ApprovalGrantIssuer:
    """Mints and verifies approval grants against a single signing secret.

    Burned nonces are held in memory. A process restart therefore invalidates
    outstanding grants rather than accepting them again; that direction of
    failure is the safe one, and it is stated in the README.
    """

    def __init__(self, signing_secret: bytes):
        if not signing_secret or len(signing_secret) < 16:
            raise ValueError("Approval grant signing secret must be at least 16 bytes.")
        self._secret = signing_secret
        self._burned_nonces: set[str] = set()

    # -- minting -----------------------------------------------------------

    def issue(self, action_id: str, payload_hash: str, expires_at_epoch: float) -> str:
        claims = {
            "aid": action_id,
            "ph": payload_hash,
            "exp": round(float(expires_at_epoch), 3),
            "nonce": secrets.token_urlsafe(12),
        }
        body = _b64url_encode(json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        return f"{GRANT_VERSION}.{body}.{self._sign(body)}"

    def _sign(self, body: str) -> str:
        digest = hmac.new(self._secret, body.encode("ascii"), hashlib.sha256).digest()
        return _b64url_encode(digest)

    # -- verification ------------------------------------------------------

    def verify(
        self,
        grant: str,
        action_id: str,
        payload_hash: str,
        now_epoch: float | None = None,
        burn_on_success: bool = True,
    ) -> GrantVerdict:
        now = time.time() if now_epoch is None else now_epoch

        if not isinstance(grant, str) or grant.count(".") != 2:
            return GrantVerdict(False, GrantRefusal.MALFORMED, "Grant is not a three-part v1 token.")

        version, body, signature = grant.split(".")
        if version != GRANT_VERSION:
            return GrantVerdict(False, GrantRefusal.MALFORMED, f"Unsupported grant version '{version}'.")

        # Constant-time comparison before the claims are trusted at all.
        if not hmac.compare_digest(self._sign(body), signature):
            return GrantVerdict(False, GrantRefusal.BAD_SIGNATURE, "HMAC-SHA256 signature mismatch.")

        try:
            claims = json.loads(_b64url_decode(body))
        except Exception:  # noqa: BLE001 - any decode failure is the same refusal
            return GrantVerdict(False, GrantRefusal.MALFORMED, "Grant claims are not decodable JSON.")

        if not isinstance(claims, dict) or not {"aid", "ph", "exp", "nonce"} <= set(claims):
            return GrantVerdict(False, GrantRefusal.MALFORMED, "Grant claims are incomplete.")

        if claims["aid"] != action_id:
            return GrantVerdict(False, GrantRefusal.WRONG_ACTION, f"Grant is bound to action '{claims['aid']}'.")

        if claims["ph"] != payload_hash:
            return GrantVerdict(
                False, GrantRefusal.CONTENT_MISMATCH,
                "Grant is bound to a different command payload hash.",
            )

        if float(claims["exp"]) <= now:
            return GrantVerdict(False, GrantRefusal.EXPIRED, "Lease elapsed before the grant was presented.")

        nonce = str(claims["nonce"])
        if nonce in self._burned_nonces:
            return GrantVerdict(False, GrantRefusal.REPLAYED, "This grant nonce was already consumed.")

        if burn_on_success:
            self._burned_nonces.add(nonce)
        return GrantVerdict(True)

    @property
    def burned_count(self) -> int:
        return len(self._burned_nonces)
