"""
Output Observer for parsing terminal logs and extracting interesting bits.
"""
import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ObservedEvent:
    """Represents an interesting event found in the output."""
    line_number: int
    line: str
    event_type: str  # "error", "warning", "info", "traceback"
    context: List[str]  # Surrounding lines for context


class OutputObserver:
    """
    Parses raw terminal logs to extract "interesting bits".
    Looks for errors, tracebacks, warnings, and other notable output.
    """

    # Patterns for detecting interesting lines
    ERROR_PATTERNS = [
        (r'^error[:\s]', 'error'),
        (r'^Error[:\s]', 'error'),
        (r'^ERROR[:\s]', 'error'),
        (r'^E:\s', 'error'),  # apt-get style
        (r'fatal error', 'error'),
        (r'FATAL', 'error'),
        (r'failed', 'error'),
        (r'FAILED', 'error'),
        (r'cannot find', 'error'),
        (r'not found', 'error'),
        (r'No such file', 'error'),
        (r'Permission denied', 'error'),
        (r'command not found', 'error'),
        (r'Unable to locate', 'error'),
        (r'returned a non-zero', 'error'),
        (r'exit code[:\s]*[1-9]', 'error'),
        (r'exit status[:\s]*[1-9]', 'error'),
    ]

    WARNING_PATTERNS = [
        (r'^warning[:\s]', 'warning'),
        (r'^Warning[:\s]', 'warning'),
        (r'^WARNING[:\s]', 'warning'),
        (r'^W:\s', 'warning'),  # apt-get style
        (r'deprecated', 'warning'),
        (r'DEPRECATED', 'warning'),
    ]

    TRACEBACK_PATTERNS = [
        (r'^Traceback \(most recent call last\)', 'traceback'),
        (r'^\s+File ".*", line \d+', 'traceback'),
        (r'^[A-Za-z]*Error:', 'traceback'),
        (r'^[A-Za-z]*Exception:', 'traceback'),
        (r'panic:', 'traceback'),  # Go
        (r'at .*\(.*:\d+:\d+\)', 'traceback'),  # JavaScript
    ]

    INFO_PATTERNS = [
        (r'^Step \d+/\d+', 'info'),  # Docker build steps
        (r'Successfully', 'info'),
        (r'Completed', 'info'),
        (r'Done', 'info'),
    ]

    def __init__(self, context_lines: int = 3):
        """
        Initialize the observer.

        Args:
            context_lines: Number of lines before/after to include as context
        """
        self.context_lines = context_lines
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile all regex patterns for efficiency."""
        self._patterns = []
        for pattern, event_type in (
            self.ERROR_PATTERNS +
            self.WARNING_PATTERNS +
            self.TRACEBACK_PATTERNS +
            self.INFO_PATTERNS
        ):
            self._patterns.append((re.compile(pattern, re.IGNORECASE), event_type))

    def observe(self, output: str) -> List[ObservedEvent]:
        """
        Parse output and extract interesting events.

        Args:
            output: Raw terminal output

        Returns:
            List of ObservedEvent objects
        """
        lines = output.split('\n')
        events = []
        seen_lines = set()  # Avoid duplicate events

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue

            for pattern, event_type in self._patterns:
                if pattern.search(stripped):
                    if i not in seen_lines:
                        seen_lines.add(i)
                        # Get context lines
                        start = max(0, i - self.context_lines)
                        end = min(len(lines), i + self.context_lines + 1)
                        context = lines[start:end]

                        events.append(ObservedEvent(
                            line_number=i + 1,
                            line=stripped,
                            event_type=event_type,
                            context=context
                        ))
                    break  # Only match first pattern per line

        return events

    def get_errors(self, output: str) -> List[ObservedEvent]:
        """Get only error events from output."""
        events = self.observe(output)
        return [e for e in events if e.event_type in ('error', 'traceback')]

    def get_summary(self, output: str) -> str:
        """
        Get a summary of interesting events in the output.

        Args:
            output: Raw terminal output

        Returns:
            Human-readable summary string
        """
        events = self.observe(output)

        if not events:
            return "No notable events detected in output."

        error_count = sum(1 for e in events if e.event_type in ('error', 'traceback'))
        warning_count = sum(1 for e in events if e.event_type == 'warning')

        lines = [f"Detected {len(events)} notable events ({error_count} errors, {warning_count} warnings):"]

        for event in events[:10]:  # Limit to first 10
            icon = "❌" if event.event_type in ('error', 'traceback') else "⚠️" if event.event_type == 'warning' else "ℹ️"
            lines.append(f"  {icon} Line {event.line_number}: {event.line[:100]}")

        if len(events) > 10:
            lines.append(f"  ... and {len(events) - 10} more events")

        return "\n".join(lines)

    def extract_error_message(self, output: str) -> Optional[str]:
        """
        Extract the most relevant error message from output.

        Args:
            output: Raw terminal output

        Returns:
            The most relevant error message, or None if no errors found
        """
        errors = self.get_errors(output)
        if not errors:
            return None

        # Prefer traceback errors as they're usually most informative
        tracebacks = [e for e in errors if e.event_type == 'traceback']
        if tracebacks:
            # Return the last traceback line (usually the actual error)
            return tracebacks[-1].line

        # Otherwise return the first error
        return errors[0].line
