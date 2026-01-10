"""
File Editor for safe file operations.
Uses search/replace to save tokens and preserve context.
"""
import os
from typing import Optional


class FileEditorError(Exception):
    """Base exception for FileEditor errors."""
    pass


class SearchTextNotFoundError(FileEditorError):
    """Raised when search text is not found in file."""
    pass


class MultipleMatchesError(FileEditorError):
    """Raised when search text is found multiple times."""
    pass


class FileEditor:
    """
    Safe file editor that uses search/replace operations.
    Designed to minimize token usage and preserve file context.
    """

    def __init__(self, root: str = "."):
        """
        Initialize the FileEditor.

        Args:
            root: Root directory for all file operations
        """
        self.root = os.path.abspath(root)

    def _resolve_path(self, path: str) -> str:
        """
        Resolve a path relative to the root directory.

        Args:
            path: Relative or absolute path

        Returns:
            Absolute path within the root directory
        """
        if os.path.isabs(path):
            return path
        return os.path.join(self.root, path)

    def _ensure_parent_dir(self, path: str):
        """Ensure the parent directory exists."""
        parent = os.path.dirname(path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)

    def read_file(self, path: str) -> str:
        """
        Read the contents of a file.

        Args:
            path: Path to the file (relative to root)

        Returns:
            File contents as string

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        full_path = self._resolve_path(path)
        with open(full_path, 'r', encoding='utf-8') as f:
            return f.read()

    def write_file(self, path: str, content: str) -> None:
        """
        Write content to a file (creates or overwrites).

        Args:
            path: Path to the file (relative to root)
            content: Content to write
        """
        full_path = self._resolve_path(path)
        self._ensure_parent_dir(full_path)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)

    def replace_block(
        self,
        path: str,
        search_text: str,
        replace_text: str,
        allow_multiple: bool = False
    ) -> int:
        """
        Replace a block of text in a file.

        This is the preferred method for modifications as it:
        - Saves tokens (only send search/replace, not full file)
        - Preserves context (doesn't overwrite entire file)
        - Is strict about matches (fails if ambiguous)

        Args:
            path: Path to the file (relative to root)
            search_text: Text to search for (must be exact match)
            replace_text: Text to replace with
            allow_multiple: If True, replace all occurrences. If False, error on multiple matches.

        Returns:
            Number of replacements made

        Raises:
            SearchTextNotFoundError: If search_text is not found
            MultipleMatchesError: If search_text is found multiple times and allow_multiple is False
        """
        full_path = self._resolve_path(path)

        # Read current content
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Count occurrences
        count = content.count(search_text)

        if count == 0:
            raise SearchTextNotFoundError(
                f"Search text not found in {path}:\n"
                f"Looking for: {search_text[:100]}{'...' if len(search_text) > 100 else ''}"
            )

        if count > 1 and not allow_multiple:
            raise MultipleMatchesError(
                f"Search text found {count} times in {path}. "
                f"Use allow_multiple=True to replace all, or provide more specific search text."
            )

        # Perform replacement
        new_content = content.replace(search_text, replace_text, -1 if allow_multiple else 1)

        # Write back
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        return count if allow_multiple else 1

    def insert_after(self, path: str, search_text: str, insert_text: str) -> None:
        """
        Insert text after a search pattern.

        Args:
            path: Path to the file
            search_text: Text to search for
            insert_text: Text to insert after the search text
        """
        self.replace_block(path, search_text, search_text + insert_text)

    def insert_before(self, path: str, search_text: str, insert_text: str) -> None:
        """
        Insert text before a search pattern.

        Args:
            path: Path to the file
            search_text: Text to search for
            insert_text: Text to insert before the search text
        """
        self.replace_block(path, search_text, insert_text + search_text)

    def delete_block(self, path: str, search_text: str) -> None:
        """
        Delete a block of text from a file.

        Args:
            path: Path to the file
            search_text: Text to delete
        """
        self.replace_block(path, search_text, "")

    def file_exists(self, path: str) -> bool:
        """Check if a file exists."""
        full_path = self._resolve_path(path)
        return os.path.isfile(full_path)

    def list_files(self, pattern: str = "*") -> list:
        """
        List files in the root directory.

        Args:
            pattern: Glob pattern to match

        Returns:
            List of file paths relative to root
        """
        import glob
        full_pattern = os.path.join(self.root, pattern)
        files = glob.glob(full_pattern, recursive=True)
        return [os.path.relpath(f, self.root) for f in files if os.path.isfile(f)]

    def get_file_info(self, path: str) -> dict:
        """
        Get information about a file.

        Args:
            path: Path to the file

        Returns:
            Dict with file info (size, lines, etc.)
        """
        full_path = self._resolve_path(path)
        stat = os.stat(full_path)

        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.count('\n') + 1

        return {
            "path": path,
            "size_bytes": stat.st_size,
            "lines": lines,
            "modified": stat.st_mtime
        }
