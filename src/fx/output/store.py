"""持久化层（stdlib sqlite3，零额外依赖）。

存两类数据：
- 最近一轮扫描结果快照（JSON），供看板/重启后查询。
- 订阅（用户 → 关注的清单或币种），供命中时 @ 推送。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import List, Optional, Tuple


class Store:
    def __init__(self, path: str = "fx.db"):
        self.path = path
        # check_same_thread=False: FastAPI 把同步路由丢进 threadpool，连接需跨线程复用。
        # 配合 self._lock 串行化访问，避免跨线程交叠事务。
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init()

    def _init(self):
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS scan_result (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    as_of TEXT, payload TEXT
                );
                CREATE TABLE IF NOT EXISTS subscription (
                    user_id TEXT, target TEXT,
                    PRIMARY KEY (user_id, target)
                );
                """
            )
            self._conn.commit()

    # ---- 扫描结果 ----
    def save_result(self, summary: dict):
        with self._lock:
            self._conn.execute(
                "INSERT INTO scan_result(id, as_of, payload) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET as_of=excluded.as_of, payload=excluded.payload",
                (summary.get("as_of"), json.dumps(summary, ensure_ascii=False)),
            )
            self._conn.commit()

    def load_result(self) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM scan_result WHERE id=1").fetchone()
        return json.loads(row["payload"]) if row else None

    # ---- 订阅 ----
    def add_subscription(self, user_id: str, target: str) -> bool:
        """target 形如 'top'/'bottom'/'squeeze'/'watch' 或某币种符号。新增返回 True。"""
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO subscription(user_id, target) VALUES (?, ?)",
                    (user_id, target.upper() if "/" in target or target.isupper() else target),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_subscription(self, user_id: str, target: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM subscription WHERE user_id=? AND target=?",
                (user_id, target),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def list_subscriptions(self, user_id: str) -> List[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT target FROM subscription WHERE user_id=? ORDER BY target",
                (user_id,),
            ).fetchall()
        return [r["target"] for r in rows]

    def all_subscriptions(self) -> List[Tuple[str, str]]:
        with self._lock:
            rows = self._conn.execute("SELECT user_id, target FROM subscription").fetchall()
        return [(r["user_id"], r["target"]) for r in rows]

    def close(self):
        with self._lock:
            self._conn.close()
