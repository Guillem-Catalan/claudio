import os
import time

import anthropic

_client = anthropic.Anthropic(
    base_url=os.environ["AZURE_CLAUDE_ENDPOINT"],
    api_key=os.environ["AZURE_CLAUDE_API_KEY"],
    default_headers={
        "api-key": os.environ["AZURE_CLAUDE_API_KEY"],
        "api-version": "2024-10-01",
    },
)

_MODEL = os.environ.get("AZURE_CLAUDE_DEPLOYMENT") or "claude-opus-4-6"
_MODEL_FAST = os.environ.get("AZURE_CLAUDE_FAST_DEPLOYMENT") or "claude-haiku-4-5"


def analyze(system_prompt: str, user_prompt: str, *, model: str | None = None, max_tokens: int = 16000) -> str:
    use_model = model or _MODEL
    last_err = None
    for attempt in range(3):
        try:
            message = _client.messages.create(
                model=use_model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return message.content[0].text.strip()
        except Exception as e:
            last_err = e
            wait = 10 * (2 ** attempt)
            print(f"  [retry {attempt + 1}/3] Azure error ({use_model}): {e} — waiting {wait}s")
            time.sleep(wait)
    raise last_err
