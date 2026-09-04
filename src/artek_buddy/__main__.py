from __future__ import annotations

import os
import sys

from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore

USAGE = (
    "usage: python -m artek_buddy "
    "pair|worker|supervisor|memory-gateway|credential-broker|"
    "credential-executor|credential-migrate"
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


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["pair"]:
        return pair()
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
    if args == ["credential-executor"]:
        from artek_buddy.credential_executor import main as executor_main

        return executor_main()
    if args == ["credential-migrate"]:
        from artek_buddy.credential_broker import migration_main

        return migration_main()
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
