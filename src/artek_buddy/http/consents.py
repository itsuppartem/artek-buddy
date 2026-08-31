from __future__ import annotations

import base64
import logging

from fastapi import Depends, HTTPException

from artek_buddy.consent import ConsentHub
from artek_buddy.contracts import (
    ConsentAnswerInput,
    ConsentFileInput,
    ConsentJob,
    ConsentResultInput,
    OkResponse,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("artek_buddy")

from fastapi import APIRouter

from artek_buddy.http.deps import (
    consent,
    require_auth,
)

router = APIRouter()


@router.get("/v1/consents/{consent_id}")
async def get_consent(
    consent_id: str,
    _actor: str = Depends(require_auth),
    hub: ConsentHub = Depends(consent),
) -> ConsentJob:
    job = hub.get_job(consent_id)
    if job is None:
        raise HTTPException(status_code=404, detail="consent not found")
    return ConsentJob.model_validate(job)


@router.post("/v1/consents/{consent_id}")
async def answer_consent(
    consent_id: str,
    body: ConsentAnswerInput,
    actor: str = Depends(require_auth),
    hub: ConsentHub = Depends(consent),
) -> OkResponse:
    row = hub.answer(consent_id, body.decision, None if actor == "host" else actor)
    if row is None:
        if hub.get_job(consent_id) is None:
            raise HTTPException(status_code=404, detail="consent not found")
        raise HTTPException(status_code=400, detail="consent not pending")
    return OkResponse(ok=True)


@router.post("/v1/consents/{consent_id}/ack")
async def acknowledge_consent_job(
    consent_id: str,
    _actor: str = Depends(require_auth),
    hub: ConsentHub = Depends(consent),
) -> OkResponse:
    if hub.acknowledge_owner_job(consent_id):
        return OkResponse(ok=True)
    if hub.get_job(consent_id) is None:
        raise HTTPException(status_code=404, detail="consent not found")
    raise HTTPException(status_code=409, detail="owner job is not queued")


@router.post("/v1/consents/{consent_id}/file")
async def upload_consent_file(
    consent_id: str,
    body: ConsentFileInput,
    _actor: str = Depends(require_auth),
    hub: ConsentHub = Depends(consent),
) -> OkResponse:
    data = b""
    if body.content_base64:
        try:
            data = base64.b64decode(body.content_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid content_base64") from exc
    elif body.text is not None:
        data = body.text.encode()
    else:
        raise HTTPException(status_code=400, detail="text or content_base64 required")
    if len(data) > 1_000_000:
        raise HTTPException(status_code=400, detail="file is larger than 1 MB")
    if not hub.put_owner_file(consent_id, body.name, data):
        if hub.get_job(consent_id) is None:
            raise HTTPException(status_code=404, detail="consent not found")
        raise HTTPException(status_code=409, detail="owner job no longer accepts files")
    if not hub.put_owner_result(
        consent_id,
        {
            "ok": True,
            "name": body.name,
            "bytes": len(data),
            "_data": data,
            "content_base64": body.content_base64,
            "text": body.text,
        },
    ):
        raise HTTPException(status_code=409, detail="owner job no longer accepts results")
    return OkResponse(ok=True)


@router.post("/v1/consents/{consent_id}/result")
async def upload_consent_result(
    consent_id: str,
    body: ConsentResultInput,
    _actor: str = Depends(require_auth),
    hub: ConsentHub = Depends(consent),
) -> OkResponse:
    payload = body.model_dump(exclude_none=True)
    if body.content_base64:
        try:
            payload["_data"] = base64.b64decode(body.content_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="invalid content_base64") from exc
    elif body.text is not None and "_data" not in payload:
        payload["_data"] = body.text.encode()
    if not hub.put_owner_result(consent_id, payload):
        if hub.get_job(consent_id) is None:
            raise HTTPException(status_code=404, detail="consent not found")
        raise HTTPException(status_code=409, detail="owner job no longer accepts results")
    return OkResponse(ok=True)
