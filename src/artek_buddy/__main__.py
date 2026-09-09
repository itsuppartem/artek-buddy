from __future__ import annotations

import os
import sys

from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore

USAGE = (
    "usage: python -m artek_buddy "
    "pair|audit-verify|audit-export|jobs-dead|worker|supervisor|memory-gateway|credential-broker|"
    "credential-migrate"
)


def pair() -> int:
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql://artek:artek@127.0.0.1:5432/artek_buddy",
    )
    store = HistoryStore(url)
    try:
        store.open()
        store.apply_migrations()
        minted = store.create_pairing_code()
    except DatabaseUnavailable as err:
        print(f"pairing failed: {err}", file=sys.stderr)
        return 1
    finally:
        store.close()
    print(minted.code)
    print(minted.expires_at)
    return 0


def audit_verify() -> int:
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql://artek:artek@127.0.0.1:5432/artek_buddy",
    )
    store = HistoryStore(url)
    try:
        store.open()
        store.apply_migrations()
        res = store.verify_audit()
    except DatabaseUnavailable as err:
        print(f"audit verification database error: {err}", file=sys.stderr)
        return 1
    finally:
        store.close()

    if not res.ok:
        print(
            f"AUDIT INTEGRITY VIOLATION at seq {res.failed_seq}: {res.reason}",
            file=sys.stderr,
        )
        return 1
    print(f"Audit chain valid: {res.total_events} events verified (head: {res.head_hash})")
    return 0


def audit_export() -> int:
    import json

    url = os.environ.get(
        "DATABASE_URL",
        "postgresql://artek:artek@127.0.0.1:5432/artek_buddy",
    )
    store = HistoryStore(url)
    try:
        store.open()
        store.apply_migrations()
        records = store.get_audit_chain()
    except DatabaseUnavailable as err:
        print(f"audit export database error: {err}", file=sys.stderr)
        return 1
    finally:
        store.close()

    data = [r.to_dict() for r in records]
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


def jobs_dead() -> int:
    import json

    url = os.environ.get(
        "DATABASE_URL",
        "postgresql://artek:artek@127.0.0.1:5432/artek_buddy",
    )
    store = HistoryStore(url)
    try:
        store.open()
        store.apply_migrations()
        dead = store.list_dead_jobs()
    except DatabaseUnavailable as err:
        print(f"dead jobs listing database error: {err}", file=sys.stderr)
        return 1
    finally:
        store.close()

    data = [j.to_dict(redact=True) for j in dead]
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["pair"]:
        return pair()
    if args == ["audit-verify"]:
        return audit_verify()
    if args == ["audit-export"]:
        return audit_export()
    if args == ["jobs-dead"]:
        return jobs_dead()
    if args == ["worker"] or args == ["worker", "--once"]:
        from artek_buddy.worker import worker

        return worker(once=args[-1:] == ["--once"])
    if args == ["supervisor"]:
        from artek_buddy.supervisor.server import main as supervisor_main

        return supervisor_main()
    if args == ["memory-gateway"]:
        from artek_buddy.memory_gateway import main as gateway_main

        return gateway_main()
    if args == ["credential-broker"]:
        from artek_buddy.credential_broker import main as broker_main

        return broker_main()
    if args == ["credential-migrate"]:
        from artek_buddy.credential_broker import migration_main

        return migration_main()
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
