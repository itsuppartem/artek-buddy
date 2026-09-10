from artek_buddy.db.history.activity import ActivityMixin
from artek_buddy.db.history.asks import AsksMixin
from artek_buddy.db.history.audit import AuditMixin
from artek_buddy.db.history.automations import AutomationsMixin
from artek_buddy.db.history.books import BooksMixin
from artek_buddy.db.history.bots import BotsMixin
from artek_buddy.db.history.computer import ComputerMixin
from artek_buddy.db.history.connections import ConnectionsMixin
from artek_buddy.db.history.consents import ConsentsMixin
from artek_buddy.db.history.devices import DevicesMixin
from artek_buddy.db.history.inbox import InboxMixin
from artek_buddy.db.history.jobs import JobsMixin
from artek_buddy.db.history.members import MembersMixin
from artek_buddy.db.history.memory import MemoryMixin
from artek_buddy.db.history.messages import MessagesMixin
from artek_buddy.db.history.models import ModelsMixin
from artek_buddy.db.history.recovery import RecoveryMixin
from artek_buddy.db.history.routines import RoutinesMixin
from artek_buddy.db.history.search import SearchMixin
from artek_buddy.db.history.store import HistoryStoreCore, InboxFullError, MigrationChecksumError
from artek_buddy.db.history.subagents import SubagentsMixin
from artek_buddy.db.history.turns import TurnsMixin
from artek_buddy.db.history.usage import UsageMixin

__all__ = ["HistoryStore", "InboxFullError", "MigrationChecksumError"]


class HistoryStore(
    HistoryStoreCore,
    ActivityMixin,
    AsksMixin,
    AuditMixin,
    AutomationsMixin,
    BooksMixin,
    BotsMixin,
    MessagesMixin,
    TurnsMixin,
    InboxMixin,
    JobsMixin,
    SubagentsMixin,
    ConsentsMixin,
    DevicesMixin,
    MembersMixin,
    RoutinesMixin,
    SearchMixin,
    MemoryMixin,
    ComputerMixin,
    ModelsMixin,
    ConnectionsMixin,
    UsageMixin,
    RecoveryMixin,
):
    pass
