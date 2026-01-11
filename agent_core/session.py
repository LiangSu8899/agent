"""
Session management with SQLite persistence.
"""
import os
import sqlite3
import threading
import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from .terminal import PTYTerminal


class SessionStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    EXITED = "EXITED"
    FAILED = "FAILED"


class Session:
    """Represents a single execution session."""

    def __init__(self, session_id: str, command: str, log_dir: str):
        self.session_id = session_id
        self.command = command
        self.status = SessionStatus.PENDING
        self.terminal: Optional[PTYTerminal] = None
        self.log_file = os.path.join(log_dir, f"{session_id}.log")
        self._log_lock = threading.Lock()
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitor = threading.Event()

        # Ensure log directory exists
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

        # Create empty log file
        with open(self.log_file, 'w') as f:
            pass

    def _append_log(self, data: str):
        """Thread-safe log appending."""
        with self._log_lock:
            with open(self.log_file, 'a') as f:
                f.write(data)

    def start(self):
        """Start the session."""
        self.terminal = PTYTerminal(
            command=self.command,
            on_output=self._append_log
        )
        self.terminal.start()
        self.status = SessionStatus.RUNNING

        # Start monitor thread to detect completion
        self._stop_monitor.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_process, daemon=True)
        self._monitor_thread.start()

    def _monitor_process(self):
        """Monitor the process for completion."""
        while not self._stop_monitor.is_set():
            if self.terminal and not self.terminal.is_paused():
                if not self.terminal.is_running():
                    if self.status == SessionStatus.RUNNING:
                        self.status = SessionStatus.COMPLETED
                    break
            self._stop_monitor.wait(0.2)

    def pause(self):
        """Pause the session."""
        if self.terminal and self.status == SessionStatus.RUNNING:
            if self.terminal.pause():
                self.status = SessionStatus.PAUSED

    def resume(self):
        """Resume the session."""
        if self.terminal and self.status == SessionStatus.PAUSED:
            if self.terminal.resume():
                self.status = SessionStatus.RUNNING

    def get_logs(self) -> str:
        """Get all logs for this session."""
        with self._log_lock:
            if os.path.exists(self.log_file):
                with open(self.log_file, 'r') as f:
                    return f.read()
        return ""

    def terminate(self):
        """Terminate the session."""
        self._stop_monitor.set()
        if self.terminal:
            self.terminal.terminate()
        self.status = SessionStatus.EXITED


class SessionManager:
    """
    Manages multiple sessions with SQLite persistence.
    """

    def __init__(self, db_path: str = "sessions.db", log_dir: str = "agent_core/logs"):
        self.db_path = db_path
        self.log_dir = log_dir
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()

        # Ensure log directory exists
        os.makedirs(log_dir, exist_ok=True)

        # Initialize database
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                command TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                log_file TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def _update_db(self, session: Session):
        """Update session state in database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO sessions
            (session_id, command, status, created_at, updated_at, log_file)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            session.session_id,
            session.command,
            session.status.value,
            datetime.now().isoformat(),
            datetime.now().isoformat(),
            session.log_file
        ))
        conn.commit()
        conn.close()

    def create_session(self, command: str) -> str:
        """
        Create a new session.
        Returns the session ID.
        """
        session_id = str(uuid.uuid4())[:8]

        with self._lock:
            session = Session(session_id, command, self.log_dir)
            self._sessions[session_id] = session
            self._update_db(session)

        return session_id

    def start_session(self, session_id: str):
        """Start a session by ID."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.start()
                self._update_db(session)

    def complete_session(self, session_id: str):
        """Mark a session as completed."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.status = SessionStatus.COMPLETED
                if session.terminal:
                    session.terminal.terminate()
                self._update_db(session)

    def fail_session(self, session_id: str):
        """Mark a session as failed."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.status = SessionStatus.FAILED
                if session.terminal:
                    session.terminal.terminate()
                self._update_db(session)

    def pause_session(self, session_id: str):
        """Pause a running session."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.pause()
                self._update_db(session)

    def resume_session(self, session_id: str):
        """Resume a paused session."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.resume()
                self._update_db(session)

    def get_status(self, session_id: str) -> str:
        """Get the current status of a session."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                # Check if process completed while we weren't looking
                if session.status == SessionStatus.RUNNING:
                    if session.terminal and not session.terminal.is_running():
                        session.status = SessionStatus.COMPLETED
                        self._update_db(session)
                return session.status.value
        return "UNKNOWN"

    def get_logs(self, session_id: str) -> str:
        """Get logs for a session."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                return session.get_logs()
        return ""

    def terminate_session(self, session_id: str):
        """Terminate a session."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.terminate()
                self._update_db(session)

    def list_sessions(self) -> list:
        """List all sessions from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT session_id, command, status, created_at FROM sessions')
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                'session_id': row[0],
                'command': row[1],
                'status': row[2],
                'created_at': row[3]
            }
            for row in rows
        ]
