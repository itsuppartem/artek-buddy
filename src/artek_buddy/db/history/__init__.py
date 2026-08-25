from artek_buddy.db.history.asks import AsksMixin
from artek_buddy.db.history.bots import BotsMixin
from artek_buddy.db.history.computer import ComputerMixin
from artek_buddy.db.history.consents import ConsentsMixin
from artek_buddy.db.history.devices import DevicesMixin
from artek_buddy.db.history.inbox import InboxMixin
from artek_buddy.db.history.memory import MemoryMixin
from artek_buddy.db.history.messages import MessagesMixin
from artek_buddy.db.history.models import ModelsMixin
from artek_buddy.db.history.routines import RoutinesMixin
from artek_buddy.db.history.store import HistoryStoreCore, InboxFullError, MigrationChecksumError
from artek_buddy.db.history.subagents import SubagentsMixin
from artek_buddy.db.history.turns import TurnsMixin

__all__ = ["HistoryStore", "InboxFullError", "MigrationChecksumError"]


class HistoryStore(
    HistoryStoreCore,
    AsksMixin,
    BotsMixin,
    MessagesMixin,
    TurnsMixin,
    InboxMixin,
    SubagentsMixin,
    ConsentsMixin,
    DevicesMixin,
    RoutinesMixin,
    MemoryMixin,
    ComputerMixin,
    ModelsMixin,
):
    pass
