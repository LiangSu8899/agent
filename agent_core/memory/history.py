"""
History Memory for tracking agent actions and preventing repeated failures.
Uses SQLite for persistence.
"""
import hashlib
import sqlite3
from datetime import datetime
from typing import List, Optional, Dict, Any


class HistoryMemory:
    """
    Stores execution history to prevent the agent from repeating failed fixes.
    Tracks: step_id, command, output_snippet, exit_code, status, reasoning.
    """

    def __init__(self, db_path: str = "history.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                step INTEGER NOT NULL,
                command TEXT NOT NULL,
                command_hash TEXT NOT NULL,
                output TEXT,
                exit_code INTEGER,
                status TEXT NOT NULL,
                reasoning TEXT,
                created_at TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_command_hash ON history(command_hash)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_status ON history(status)
        ''')
        conn.commit()
        conn.close()

    def _hash_command(self, command: str) -> str:
        """Create a normalized hash of a command for comparison."""
        # Normalize: strip whitespace, lowercase
        normalized = command.strip().lower()
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def add_entry(
        self,
        step: int,
        command: str,
        output: str,
        exit_code: int,
        status: str,
        reasoning: str = ""
    ) -> int:
        """
        Add a new entry to the history.

        Args:
            step: Step number in the debug session
            command: The command that was executed
            output: Output/logs from the command (can be truncated)
            exit_code: Exit code of the command
            status: Status string (e.g., "SUCCESS", "FAILED")
            reasoning: The agent's reasoning for this action

        Returns:
            The ID of the inserted entry
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO history (step, command, command_hash, output, exit_code, status, reasoning, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            step,
            command,
            self._hash_command(command),
            output[:5000] if output else "",  # Truncate long outputs
            exit_code,
            status,
            reasoning,
            datetime.now().isoformat()
        ))
        entry_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return entry_id

    def has_failed_before(self, command: str) -> bool:
        """
        Check if a command (or similar) has failed before.

        Args:
            command: The command to check

        Returns:
            True if this command has failed in the past
        """
        command_hash = self._hash_command(command)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM history
            WHERE command_hash = ? AND status = 'FAILED'
        ''', (command_hash,))
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0

    def get_failure_count(self, command: str) -> int:
        """Get the number of times a command has failed."""
        command_hash = self._hash_command(command)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM history
            WHERE command_hash = ? AND status = 'FAILED'
        ''', (command_hash,))
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def get_recent_entries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the most recent history entries."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT step, command, output, exit_code, status, reasoning, created_at
            FROM history
            ORDER BY id DESC
            LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "step": row[0],
                "command": row[1],
                "output": row[2],
                "exit_code": row[3],
                "status": row[4],
                "reasoning": row[5],
                "created_at": row[6]
            }
            for row in reversed(rows)  # Return in chronological order
        ]

    def get_failed_commands(self) -> List[str]:
        """Get a list of all commands that have failed."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT command FROM history
            WHERE status = 'FAILED'
        ''')
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows]

    def get_context_for_prompt(self, max_entries: int = 5) -> str:
        """
        Generate a context string suitable for including in an LLM prompt.
        Shows recent history to help the model avoid repeating mistakes.

        Args:
            max_entries: Maximum number of entries to include

        Returns:
            Formatted string of recent history
        """
        entries = self.get_recent_entries(limit=max_entries)

        if not entries:
            return "No previous actions recorded."

        lines = ["Previous Actions:"]
        for entry in entries:
            status_icon = "✓" if entry["status"] == "SUCCESS" else "✗"
            lines.append(f"  [{status_icon}] Step {entry['step']}: {entry['command']}")
            lines.append(f"      Status: {entry['status']} (exit code: {entry['exit_code']})")
            if entry["reasoning"]:
                lines.append(f"      Reasoning: {entry['reasoning']}")
            # Include truncated output for failed commands
            if entry["status"] == "FAILED" and entry["output"]:
                output_preview = entry["output"][:200].replace('\n', ' ')
                lines.append(f"      Output: {output_preview}...")

        # Add explicit warning about failed commands
        failed = self.get_failed_commands()
        if failed:
            lines.append("\n⚠️ Failed Commands (DO NOT RETRY):")
            for cmd in failed[-5:]:  # Last 5 failed commands
                lines.append(f"  - {cmd}")

        return "\n".join(lines)

    def clear(self):
        """Clear all history entries."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM history')
        conn.commit()
        conn.close()
