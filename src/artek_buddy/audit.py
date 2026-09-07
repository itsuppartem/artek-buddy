from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

from artek_buddy.observe import redact_text

log = logging.getLogger("artek_buddy")

GENESIS_HASH = "0" * 64

# Canonical event types
AUDIT_MEMBER_CREATE = "member.create"
AUDIT_MEMBER_SUSPEND = "member.suspend"
AUDIT_MEMBER_ACTIVATE = "member.activate"
AUDIT_DEVICE_CREATE = "device.create"
AUDIT_DEVICE_REVOKE = "device.revoke"
AUDIT_INVITE_MINT = "invite.mint"
AUDIT_INVITE_CLAIM = "invite.claim"
AUDIT_INVITE_REVOKE = "invite.revoke"
AUDIT_GRANT_CHANGE = "grant.change"
AUDIT_CONSENT_DECISION = "consent.decision"
AUDIT_COLLABORATION_OFF = "emergency.collaboration_off"

_FORBIDDEN_PAYLOAD_KEYS = {
    "token",
    "token_hash",
    "secret",
    "secret_hash",
    "pairing_code",
    "code_hash",
    "password",
    "key",
}


def canonical_payload_json(payload: dict[str, Any]) -> str:
    """Format payload as canonical JSON (sorted keys, compact separators, UTF-8, no secrets)."""
    sanitized: dict[str, Any] = {}
    for k, v in payload.items():
        if k.lower() in _FORBIDDEN_PAYLOAD_KEYS:
            continue
        if isinstance(v, str):
            sanitized[k] = redact_text(v)
        else:
            sanitized[k] = v
    return json.dumps(sanitized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_audit_hash(
    seq: int,
    event_type: str,
    actor: str,
    resource: str,
    payload_json: str,
    prev_hash: str,
) -> str:
    raw = f"{seq}:{event_type}:{actor}:{resource}:{payload_json}:{prev_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class AuditRecord:
    seq: int
    id: str
    event_type: str
    actor: str
    resource: str
    payload: dict[str, Any]
    prev_hash: str
    hash: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AuditVerificationResult:
    ok: bool
    total_events: int
    head_hash: str
    failed_seq: int | None = None
    reason: str | None = None


def verify_audit_chain(records: list[AuditRecord]) -> AuditVerificationResult:
    if not records:
        return AuditVerificationResult(ok=True, total_events=0, head_hash=GENESIS_HASH)

    prev_record: AuditRecord | None = None
    for record in records:
        if record.seq == 1:
            if record.prev_hash != GENESIS_HASH:
                return AuditVerificationResult(
                    ok=False,
                    total_events=len(records),
                    head_hash=records[-1].hash,
                    failed_seq=record.seq,
                    reason=(
                        f"Genesis prev_hash mismatch: expected {GENESIS_HASH}, "
                        f"got {record.prev_hash}"
                    ),
                )
        else:
            if prev_record is None:
                return AuditVerificationResult(
                    ok=False,
                    total_events=len(records),
                    head_hash=records[-1].hash,
                    failed_seq=record.seq,
                    reason=f"Missing predecessor for seq {record.seq}",
                )
            if record.prev_hash != prev_record.hash:
                return AuditVerificationResult(
                    ok=False,
                    total_events=len(records),
                    head_hash=records[-1].hash,
                    failed_seq=record.seq,
                    reason=(
                        f"Broken chain at seq {record.seq}: prev_hash {record.prev_hash} "
                        f"!= predecessor hash {prev_record.hash}"
                    ),
                )
            if record.seq != prev_record.seq + 1:
                return AuditVerificationResult(
                    ok=False,
                    total_events=len(records),
                    head_hash=records[-1].hash,
                    failed_seq=record.seq,
                    reason=f"Sequence gap: seq {record.seq} != {prev_record.seq + 1}",
                )

        payload_json = canonical_payload_json(record.payload)
        expected_hash = compute_audit_hash(
            record.seq,
            record.event_type,
            record.actor,
            record.resource,
            payload_json,
            record.prev_hash,
        )
        if record.hash != expected_hash:
            return AuditVerificationResult(
                ok=False,
                total_events=len(records),
                head_hash=records[-1].hash,
                failed_seq=record.seq,
                reason=f"Hash mismatch at seq {record.seq}: {record.hash} != {expected_hash}",
            )

        prev_record = record

    return AuditVerificationResult(
        ok=True,
        total_events=len(records),
        head_hash=records[-1].hash,
    )
