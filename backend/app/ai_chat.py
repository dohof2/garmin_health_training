"""Public entry point for the single skill-based conversational agent."""
MAX_MESSAGE_LENGTH = 4000
MAX_HISTORY_MESSAGES = 20


def _validated_messages(
    message: object,
    history: object,
) -> tuple[str, list[dict[str, str]]]:
    text = str(message or "").strip()
    if not text:
        raise ValueError("message is required")
    if len(text) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"message must be {MAX_MESSAGE_LENGTH} characters or fewer")
    if history is None:
        history = []
    if not isinstance(history, list) or len(history) > MAX_HISTORY_MESSAGES:
        raise ValueError(f"history must contain at most {MAX_HISTORY_MESSAGES} messages")

    validated: list[dict[str, str]] = []
    for item in history:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            raise ValueError("history messages must have user or assistant roles")
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("history messages require text content")
        if len(content) > MAX_MESSAGE_LENGTH:
            raise ValueError(
                f"history message must be {MAX_MESSAGE_LENGTH} characters or fewer"
            )
        validated.append({"role": str(item["role"]), "content": content.strip()})
    return text, validated


def chat_stream(message, history=None, timezone_name=None, path=None, **kwargs):
    from .skill_agent import stream
    yield from stream(message, history, timezone_name, path, **kwargs)
