"""
Token counting utilities for context management.
Supports tiktoken (if available) or falls back to simple approximation.
"""
from typing import Optional

# Try to import tiktoken, fall back to approximation if not available
_tiktoken_available = False
_encoder = None

try:
    import tiktoken
    _tiktoken_available = True
    # Use cl100k_base encoding (used by GPT-4, similar to most modern models)
    _encoder = tiktoken.get_encoding("cl100k_base")
except ImportError:
    pass


def count_tokens(text: str, model: Optional[str] = None) -> int:
    """
    Count the number of tokens in a text string.

    Uses tiktoken if available, otherwise falls back to a simple
    word-based approximation (roughly 4 characters per token).

    Args:
        text: The text to count tokens for
        model: Optional model name for model-specific tokenization

    Returns:
        Estimated number of tokens
    """
    if not text:
        return 0

    if _tiktoken_available and _encoder is not None:
        return len(_encoder.encode(text))
    else:
        # Simple approximation: ~4 characters per token on average
        # This is a rough estimate based on typical English text
        return max(1, len(text) // 4)


def count_tokens_messages(messages: list, model: Optional[str] = None) -> int:
    """
    Count tokens for a list of chat messages.

    Args:
        messages: List of message dicts with 'role' and 'content' keys
        model: Optional model name

    Returns:
        Total token count including message overhead
    """
    total = 0
    for msg in messages:
        # Add overhead for message structure (~4 tokens per message)
        total += 4
        if 'role' in msg:
            total += count_tokens(msg['role'], model)
        if 'content' in msg:
            total += count_tokens(msg['content'], model)
    # Add base overhead for the conversation
    total += 2
    return total


def truncate_to_token_limit(text: str, max_tokens: int, model: Optional[str] = None) -> str:
    """
    Truncate text to fit within a token limit.

    Args:
        text: The text to truncate
        max_tokens: Maximum number of tokens allowed
        model: Optional model name

    Returns:
        Truncated text that fits within the token limit
    """
    if count_tokens(text, model) <= max_tokens:
        return text

    if _tiktoken_available and _encoder is not None:
        tokens = _encoder.encode(text)
        truncated_tokens = tokens[:max_tokens]
        return _encoder.decode(truncated_tokens)
    else:
        # Approximate truncation based on character count
        chars_per_token = 4
        max_chars = max_tokens * chars_per_token
        return text[:max_chars]


def estimate_context_usage(
    system_prompt: str,
    messages: list,
    max_context: int = 4096,
    model: Optional[str] = None
) -> dict:
    """
    Estimate context window usage.

    Args:
        system_prompt: The system prompt
        messages: List of conversation messages
        max_context: Maximum context window size
        model: Optional model name

    Returns:
        Dict with usage statistics
    """
    system_tokens = count_tokens(system_prompt, model)
    message_tokens = count_tokens_messages(messages, model)
    total_tokens = system_tokens + message_tokens

    return {
        "system_tokens": system_tokens,
        "message_tokens": message_tokens,
        "total_tokens": total_tokens,
        "max_context": max_context,
        "remaining_tokens": max(0, max_context - total_tokens),
        "usage_percent": (total_tokens / max_context) * 100 if max_context > 0 else 0
    }
