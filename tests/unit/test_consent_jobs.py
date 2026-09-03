from __future__ import annotations

from artek_buddy.consent import ConsentHub
from artek_buddy.consent_jobs import OwnerJobTransport


def test_owner_job_methods_live_on_the_transport_not_the_card_hub() -> None:
    assert ConsentHub.claim_owner_job is OwnerJobTransport.claim_owner_job
    assert ConsentHub.put_owner_result is OwnerJobTransport.put_owner_result
    assert ConsentHub.take_owner_file is OwnerJobTransport.take_owner_file
    assert ConsentHub.cancel_owner_jobs is OwnerJobTransport.cancel_owner_jobs
    assert ConsentHub.start_auto_owner_read is OwnerJobTransport.start_auto_owner_read
    assert ConsentHub.offer is not OwnerJobTransport.__dict__.get("offer")
    assert "offer" not in OwnerJobTransport.__dict__
    assert "answer" not in OwnerJobTransport.__dict__
    assert "begin_question" not in OwnerJobTransport.__dict__
