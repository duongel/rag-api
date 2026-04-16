"""Persistent per-message API call budgets for agent integrations."""

import sqlite3
import threading
from pathlib import Path
from typing import Optional, Union


class AgentCallBudgetStore:
    """Persist and enforce per-message call limits across process restarts."""

    def __init__(self, db_path: str, max_calls: int) -> None:
        self.db_path = Path(db_path)
        self.max_calls = max_calls
        self._lock = threading.Lock()
        self._ensure_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_call_counters (
                    conversation_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    call_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (conversation_id, message_id)
                )
                """
            )
            conn.commit()

    def is_enabled(self) -> bool:
        return self.max_calls > 0

    def increment_and_check(
        self,
        conversation_id: str,
        message_id: str,
    ) -> dict[str, Union[int, bool]]:
        """Atomically increment the counter and report whether the call is allowed."""
        with self._lock:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    """
                    SELECT call_count
                    FROM agent_call_counters
                    WHERE conversation_id = ? AND message_id = ?
                    """,
                    (conversation_id, message_id),
                ).fetchone()

                current_count = int(row["call_count"]) if row else 0
                next_count = current_count + 1
                allowed = next_count <= self.max_calls

                conn.execute(
                    """
                    INSERT INTO agent_call_counters (
                        conversation_id,
                        message_id,
                        call_count,
                        updated_at
                    )
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(conversation_id, message_id)
                    DO UPDATE SET
                        call_count = excluded.call_count,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (conversation_id, message_id, next_count),
                )
                conn.commit()

        remaining = max(self.max_calls - next_count, 0)
        return {
            "call_count": next_count,
            "remaining_calls": remaining,
            "allowed": allowed,
        }

    def get(
        self,
        conversation_id: str,
        message_id: str,
    ) -> dict[str, int]:
        """Return the current counter state without mutating it."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT call_count
                FROM agent_call_counters
                WHERE conversation_id = ? AND message_id = ?
                """,
                (conversation_id, message_id),
            ).fetchone()

        call_count = int(row["call_count"]) if row else 0
        return {
            "call_count": call_count,
            "remaining_calls": max(self.max_calls - call_count, 0),
        }

    def decrement(
        self,
        conversation_id: str,
        message_id: str,
    ) -> dict[str, int]:
        """Rollback one counted call when a request ultimately fails."""
        with self._lock:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    """
                    SELECT call_count
                    FROM agent_call_counters
                    WHERE conversation_id = ? AND message_id = ?
                    """,
                    (conversation_id, message_id),
                ).fetchone()

                current_count = int(row["call_count"]) if row else 0
                next_count = max(current_count - 1, 0)

                if next_count == 0:
                    conn.execute(
                        """
                        DELETE FROM agent_call_counters
                        WHERE conversation_id = ? AND message_id = ?
                        """,
                        (conversation_id, message_id),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE agent_call_counters
                        SET call_count = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE conversation_id = ? AND message_id = ?
                        """,
                        (next_count, conversation_id, message_id),
                    )
                conn.commit()

        return {
            "call_count": next_count,
            "remaining_calls": max(self.max_calls - next_count, 0),
        }

    def reset(
        self,
        conversation_id: str,
        message_id: Optional[str] = None,
    ) -> int:
        """Delete counters for one conversation/message scope."""
        with self._lock:
            with self._connect() as conn:
                if message_id is None:
                    result = conn.execute(
                        """
                        DELETE FROM agent_call_counters
                        WHERE conversation_id = ?
                        """,
                        (conversation_id,),
                    )
                else:
                    result = conn.execute(
                        """
                        DELETE FROM agent_call_counters
                        WHERE conversation_id = ? AND message_id = ?
                        """,
                        (conversation_id, message_id),
                    )
                conn.commit()
        return int(result.rowcount)
