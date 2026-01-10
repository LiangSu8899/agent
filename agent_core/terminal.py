"""
PTY-based terminal execution for real shell interactivity.
"""
import os
import pty
import select
import signal
import threading
from typing import Callable, Optional


class PTYTerminal:
    """
    Manages a pseudo-terminal for executing shell commands with full interactivity.
    Supports pause/resume functionality via SIGSTOP/SIGCONT signals.
    """

    def __init__(self, command: str, on_output: Optional[Callable[[str], None]] = None):
        self.command = command
        self.on_output = on_output
        self.master_fd: Optional[int] = None
        self.slave_fd: Optional[int] = None
        self.pid: Optional[int] = None
        self._running = False
        self._paused = False
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> int:
        """
        Start the PTY process.
        Returns the child PID.
        """
        self.master_fd, self.slave_fd = pty.openpty()

        self.pid = os.fork()

        if self.pid == 0:
            # Child process
            os.close(self.master_fd)
            os.setsid()
            os.dup2(self.slave_fd, 0)  # stdin
            os.dup2(self.slave_fd, 1)  # stdout
            os.dup2(self.slave_fd, 2)  # stderr
            os.close(self.slave_fd)
            os.execvp("/bin/bash", ["/bin/bash", "-c", self.command])
        else:
            # Parent process
            os.close(self.slave_fd)
            self.slave_fd = None
            self._running = True
            self._stop_event.clear()
            self._reader_thread = threading.Thread(target=self._read_output, daemon=True)
            self._reader_thread.start()
            return self.pid

    def _read_output(self):
        """Background thread to read PTY output."""
        while not self._stop_event.is_set():
            if self.master_fd is None:
                break
            try:
                ready, _, _ = select.select([self.master_fd], [], [], 0.1)
                if ready:
                    try:
                        data = os.read(self.master_fd, 4096)
                        if data:
                            decoded = data.decode('utf-8', errors='replace')
                            if self.on_output:
                                self.on_output(decoded)
                        else:
                            # EOF - process ended
                            break
                    except OSError:
                        break
            except (ValueError, OSError):
                break

    def pause(self) -> bool:
        """Pause the process using SIGSTOP."""
        if self.pid and self._running and not self._paused:
            try:
                os.kill(self.pid, signal.SIGSTOP)
                self._paused = True
                return True
            except ProcessLookupError:
                return False
        return False

    def resume(self) -> bool:
        """Resume the process using SIGCONT."""
        if self.pid and self._paused:
            try:
                os.kill(self.pid, signal.SIGCONT)
                self._paused = False
                return True
            except ProcessLookupError:
                return False
        return False

    def is_running(self) -> bool:
        """Check if the process is still running."""
        if self.pid is None:
            return False
        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid == 0:
                return True
            else:
                self._running = False
                return False
        except ChildProcessError:
            self._running = False
            return False

    def is_paused(self) -> bool:
        """Check if the process is paused."""
        return self._paused

    def wait(self, timeout: Optional[float] = None) -> Optional[int]:
        """Wait for the process to complete."""
        if self.pid is None:
            return None
        try:
            if timeout is not None:
                import time
                start = time.time()
                while time.time() - start < timeout:
                    pid, status = os.waitpid(self.pid, os.WNOHANG)
                    if pid != 0:
                        self._running = False
                        return os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
                    time.sleep(0.1)
                return None
            else:
                _, status = os.waitpid(self.pid, 0)
                self._running = False
                return os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
        except ChildProcessError:
            self._running = False
            return None

    def terminate(self):
        """Terminate the process."""
        if self.pid:
            try:
                if self._paused:
                    os.kill(self.pid, signal.SIGCONT)
                os.kill(self.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        self._cleanup()

    def _cleanup(self):
        """Clean up resources."""
        self._stop_event.set()
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None
        self._running = False
