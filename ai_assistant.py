"""
AI note assistant for doctors: advisory-only differential/next-step
suggestions on consultation notes. Never a diagnosis, never saved to the
patient record, never sent with patient identifiers.

Requires ANTHROPIC_API_KEY in the environment. Without it, is_configured()
is False and the feature stays disabled rather than erroring.
"""

import os

try:
    import anthropic
except ImportError:
    anthropic = None

DEFAULT_MODEL = "claude-sonnet-4-5"

SYSTEM_PROMPT = """You are assisting a licensed medical doctor who is reviewing their own \
clinical notes for a patient consultation. You are not told who the patient is.

Given the notes below, respond with brief, advisory suggestions only:
- Differential considerations worth ruling out
- Potential red flags to watch for
- Suggested next steps or investigations

Use hedged, non-definitive language throughout ("consider", "may warrant", "worth \
ruling out") — never state a diagnosis as fact. Keep the response short: a few bullet \
points per section, plain text, no markdown headers. The doctor retains full clinical \
judgment and responsibility for the patient's care."""


def is_configured() -> bool:
    return anthropic is not None and bool(os.environ.get("ANTHROPIC_API_KEY"))


def get_suggestions(notes: str) -> str:
    """Sends only the free-text notes (no patient name, number, or other
    identifiers) to the configured model. Raises RuntimeError with a
    user-facing message on any failure; callers should catch it."""
    if not is_configured():
        raise RuntimeError("AI assistant isn't configured. Set ANTHROPIC_API_KEY to enable it.")

    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    client = anthropic.Anthropic()

    try:
        response = client.messages.create(
            model=model,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": notes}],
        )
    except Exception as e:
        raise RuntimeError(f"AI assistant request failed: {e}") from e

    return "".join(block.text for block in response.content if block.type == "text").strip()
