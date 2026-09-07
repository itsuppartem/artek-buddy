from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from artek_buddy.contracts import AuditVerificationReport, Principal
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.http.deps import _db_error, require_principal, store

log = logging.getLogger("artek_buddy")

router = APIRouter()


@router.get("/v1/audit")
async def get_audit(
    principal: Principal = Depends(require_principal),
    history: HistoryStore = Depends(store),
) -> AuditVerificationReport:
    if principal.role != "owner":
        raise HTTPException(status_code=403, detail="owner role required")
    try:
        res = history.verify_audit()
        chain = history.get_audit_chain()
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    return AuditVerificationReport(
        ok=res.ok,
        total_events=res.total_events,
        head_hash=res.head_hash,
        failed_seq=res.failed_seq,
        reason=res.reason,
        events=[r.to_dict() for r in chain],
    )
