"""
對話 Checkpointer 與 Session 鎖工廠 (ADR-0019)

- memory：LangGraph InMemorySaver + TtlLruSessionRegistry（惰性過期、LRU 淘汰並刪除其 thread 檢查點）
          + 行程內 per-session threading.Lock（acquire 非阻塞，失敗 → SessionBusyError）
- redis ：langgraph-checkpoint-redis 之 RedisSaver（僅此後端才延遲匯入，未安裝不影響 memory 後端與 CLI）
          + Redis SET NX EX 分散式 Session 鎖（token 比對釋放）
連線失敗 → ChatUnavailableError（不靜默改用 memory，避免多 worker 狀態分裂）。
"""
import logging
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, List, Optional, Tuple

from src.domain.exceptions import ChatUnavailableError, SessionBusyError

logger = logging.getLogger(__name__)

REDIS_LOCK_PREFIX = "chat:v1:lock:"
REDIS_CHECKPOINT_PREFIX = "chat:v1:checkpoint"
REDIS_CHECKPOINT_WRITE_PREFIX = "chat:v1:checkpoint_write"

_RELEASE_SCRIPT = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"


class TtlLruSessionRegistry:
    """記憶體 Session 存活登錄表：最後存取時間 + TTL 惰性過期 + LRU 上限淘汰"""

    def __init__(self, ttl_seconds: float, max_sessions: int, clock: Callable[[], float] = time.monotonic):
        self._ttl = float(ttl_seconds)
        self._max = max(int(max_sessions), 1)
        self._clock = clock
        self._last_access: "OrderedDict[str, float]" = OrderedDict()
        self._lock = threading.Lock()

    def is_expired(self, session_id: str) -> bool:
        with self._lock:
            last = self._last_access.get(session_id)
            return last is not None and self._clock() - last > self._ttl

    def touch(self, session_id: str) -> Tuple[bool, List[str]]:
        """更新存取時間；回傳 (是否曾過期, 被 LRU 淘汰之 session_id 清單)"""
        with self._lock:
            now = self._clock()
            last = self._last_access.get(session_id)
            expired = last is not None and now - last > self._ttl
            self._last_access[session_id] = now
            self._last_access.move_to_end(session_id)
            evicted: List[str] = []
            while len(self._last_access) > self._max:
                old_sid, _ = self._last_access.popitem(last=False)
                evicted.append(old_sid)
            return expired, evicted

    def remove(self, session_id: str) -> None:
        with self._lock:
            self._last_access.pop(session_id, None)

    def __len__(self) -> int:
        with self._lock:
            return len(self._last_access)


class MemorySessionLock:
    """行程內 per-session 非阻塞鎖"""

    def __init__(self):
        self._locks: dict = {}
        self._guard = threading.Lock()

    @contextmanager
    def hold(self, session_id: str) -> Iterator[None]:
        # 取得與非阻塞 acquire 於同一 guard 內完成，避免與 remove() 競態
        with self._guard:
            lock = self._locks.setdefault(session_id, threading.Lock())
            acquired = lock.acquire(blocking=False)
        if not acquired:
            raise SessionBusyError("同一 Session 上一輪尚未完成")
        try:
            yield
        finally:
            lock.release()

    def remove(self, session_id: str) -> None:
        """Session 淘汰/重置時回收鎖物件；持有中者保留，避免同 Session 並行"""
        with self._guard:
            lock = self._locks.get(session_id)
            if lock is not None and not lock.locked():
                del self._locks[session_id]

    def __len__(self) -> int:
        with self._guard:
            return len(self._locks)


class RedisSessionLock:
    """Redis SET NX EX 分散式 Session 鎖"""

    def __init__(self, redis_client: Any, ttl_seconds: int, prefix: str = REDIS_LOCK_PREFIX):
        self._client = redis_client
        self._ttl = max(int(ttl_seconds), 1)
        self._prefix = prefix

    @contextmanager
    def hold(self, session_id: str) -> Iterator[None]:
        key = f"{self._prefix}{session_id}"
        token = uuid.uuid4().hex
        try:
            acquired = self._client.set(key, token, nx=True, ex=self._ttl)
        except Exception as err:
            raise ChatUnavailableError("Session 鎖服務不可用") from err
        if not acquired:
            raise SessionBusyError("同一 Session 上一輪尚未完成")
        try:
            yield
        finally:
            try:
                self._client.eval(_RELEASE_SCRIPT, 1, key, token)
            except Exception as err:
                logger.warning("Session 鎖釋放失敗，將由 TTL 自動過期 (err_type=%s)", type(err).__name__)


@dataclass
class CheckpointerBundle:
    saver: Any
    lock: Any
    registry: Optional[TtlLruSessionRegistry] = None
    closers: List[Callable[[], None]] = field(default_factory=list)

    def close(self) -> None:
        for closer in self.closers:
            try:
                closer()
            except Exception as err:
                logger.warning("Checkpointer 資源關閉異常 (err_type=%s)", type(err).__name__)


def build_memory_checkpointer(session_ttl_seconds: float, max_sessions: int,
                              clock: Callable[[], float] = time.monotonic) -> CheckpointerBundle:
    from langgraph.checkpoint.memory import InMemorySaver

    return CheckpointerBundle(
        saver=InMemorySaver(),
        lock=MemorySessionLock(),
        registry=TtlLruSessionRegistry(session_ttl_seconds, max_sessions, clock),
    )


def redis_db_hint(redis_url: str) -> str:
    """CHAT_CHECKPOINT_REDIS_URL 指向非 db0 時回傳可行動提示（RediSearch 僅支援 db0）"""
    from urllib.parse import urlparse

    try:
        parsed = urlparse(redis_url or "")
        path = (parsed.path or "").strip("/")
        db = int(path) if path else int(dict(
            p.split("=", 1) for p in (parsed.query or "").split("&") if "=" in p).get("db", 0))
    except (ValueError, TypeError):
        return ""
    if db == 0:
        return ""
    return (f"；CHAT_CHECKPOINT_REDIS_URL 指向 db{db}，但 RediSearch 僅支援 db0，"
            "請改用 db0 並以鍵前綴 (chat:v1:*) 隔離")


def build_redis_checkpointer(redis_url: str, session_ttl_seconds: float, lock_ttl_seconds: int) -> CheckpointerBundle:
    try:
        from langgraph.checkpoint.redis import RedisSaver
    except ImportError as err:
        raise ChatUnavailableError(
            "CHAT_CHECKPOINTER_BACKEND=redis 需安裝 langgraph-checkpoint-redis"
        ) from err
    try:
        import redis

        client = redis.Redis.from_url(redis_url)
        client.ping()
        saver = RedisSaver(
            redis_client=client,
            ttl={"default_ttl": max(float(session_ttl_seconds) / 60.0, 1.0), "refresh_on_read": True},
            checkpoint_prefix=REDIS_CHECKPOINT_PREFIX,
            checkpoint_write_prefix=REDIS_CHECKPOINT_WRITE_PREFIX,
        )
        saver.setup()
    except Exception as err:
        raise ChatUnavailableError(
            f"Redis Checkpointer 初始化失敗 ({type(err).__name__}){redis_db_hint(redis_url)}"
        ) from err
    return CheckpointerBundle(
        saver=saver,
        lock=RedisSessionLock(client, lock_ttl_seconds),
        registry=None,
        closers=[client.close],
    )


def build_checkpointer(backend: str, redis_url: str, session_ttl_seconds: float, max_sessions: int,
                       lock_ttl_seconds: int) -> CheckpointerBundle:
    normalized = (backend or "memory").strip().lower()
    if normalized == "memory":
        return build_memory_checkpointer(session_ttl_seconds, max_sessions)
    if normalized == "redis":
        return build_redis_checkpointer(redis_url, session_ttl_seconds, lock_ttl_seconds)
    raise ChatUnavailableError(f"不支援的 CHAT_CHECKPOINTER_BACKEND：{backend}")
