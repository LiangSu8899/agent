"""
Browser Tool for web research.
Provides search and page reading capabilities.
"""
import re
from typing import List, Dict, Optional
from urllib.parse import quote_plus

# Import requests - will be mocked in tests
import requests


class BrowserToolError(Exception):
    """Base exception for BrowserTool errors."""
    pass


class BrowserTool:
    """
    Browser tool for web research.
    Provides search functionality and page content extraction.
    """

    DEFAULT_TIMEOUT = 10  # seconds
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        """
        Initialize the BrowserTool.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.headers = {
            "User-Agent": self.DEFAULT_USER_AGENT
        }

    def search(self, query: str, num_results: int = 5) -> List[Dict[str, str]]:
        """
        Search the web for a query.

        Args:
            query: Search query string
            num_results: Maximum number of results to return

        Returns:
            List of dicts with 'title', 'url', and 'snippet' keys
        """
        try:
            # Try using duckduckgo-search if available
            from duckduckgo_search import DDGS

            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=num_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", "")
                    })
            return results

        except ImportError:
            # Fallback: return empty results if duckduckgo-search not installed
            # In production, you might use another search API
            return []

        except Exception as e:
            raise BrowserToolError(f"Search failed: {e}")

    def read_page(self, url: str) -> str:
        """
        Fetch a web page and extract clean text content.

        Args:
            url: URL to fetch

        Returns:
            Clean text content (HTML stripped)
        """
        try:
            response = requests.get(
                url,
                headers=self.headers,
                timeout=self.timeout
            )
            response.raise_for_status()

            html = response.text
            return self._extract_text(html)

        except requests.Timeout:
            raise BrowserToolError(f"Timeout fetching {url}")
        except requests.RequestException as e:
            raise BrowserToolError(f"Failed to fetch {url}: {e}")

    def _extract_text(self, html: str) -> str:
        """
        Extract clean text from HTML, stripping scripts, styles, and tags.

        Args:
            html: Raw HTML content

        Returns:
            Clean text content
        """
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, 'html.parser')

            # Remove script and style elements
            for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                element.decompose()

            # Get text
            text = soup.get_text(separator='\n')

            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)

            return text

        except ImportError:
            # Fallback: basic regex-based HTML stripping
            return self._strip_html_basic(html)

    def _strip_html_basic(self, html: str) -> str:
        """
        Basic HTML stripping using regex (fallback if BeautifulSoup not available).

        Args:
            html: Raw HTML content

        Returns:
            Text with HTML tags removed
        """
        # Remove script and style content
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        html = re.sub(r'<[^>]+>', ' ', html)

        # Decode HTML entities
        html = html.replace('&nbsp;', ' ')
        html = html.replace('&amp;', '&')
        html = html.replace('&lt;', '<')
        html = html.replace('&gt;', '>')
        html = html.replace('&quot;', '"')

        # Clean up whitespace
        html = re.sub(r'\s+', ' ', html)
        html = html.strip()

        return html

    def read_page_summary(self, url: str, max_length: int = 2000) -> str:
        """
        Fetch a page and return a truncated summary.

        Args:
            url: URL to fetch
            max_length: Maximum length of returned text

        Returns:
            Truncated text content
        """
        content = self.read_page(url)
        if len(content) > max_length:
            return content[:max_length] + "..."
        return content

    def fetch_raw(self, url: str) -> str:
        """
        Fetch raw HTML content without processing.

        Args:
            url: URL to fetch

        Returns:
            Raw HTML content
        """
        try:
            response = requests.get(
                url,
                headers=self.headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.text

        except requests.Timeout:
            raise BrowserToolError(f"Timeout fetching {url}")
        except requests.RequestException as e:
            raise BrowserToolError(f"Failed to fetch {url}: {e}")
