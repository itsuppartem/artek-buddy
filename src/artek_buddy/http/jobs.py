from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from artek_buddy.contracts import DeadJob, DeadJobList, Principal
from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.http.deps import _db_error, require_principal, store

log = logging.getLogger("artek_buddy.jobs")

router = APIRouter()


@router.get("/v1/jobs/dead")
async def list_dead_jobs(
    principal: Principal = Depends(require_principal),
    history: HistoryStore = Depends(store),
) -> DeadJobList:
    if principal.role != "owner":
        raise HTTPException(status_code=403, detail="owner role required")
    try:
        dead = history.list_dead_jobs()
    except DatabaseUnavailable as err:
        raise _db_error(err) from err
    return DeadJobList(
        jobs=[
            DeadJob(
                id=j.id,
                job_type=j.job_type,
                resource_id=j.resource_id,
                idempotency_key=j.idempotency_key,
                state=j.state,
                payload=j.to_dict(redact=True)["payload"],
                last_error=j.last_error,
                attempts=j.attempts,
                max_attempts=j.max_attempts,
                created_at=j.created_at,
                updated_at=j.updated_at,
            )
            for j in dead
        ]
    )
