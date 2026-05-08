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

_MODEL = os.environ.get("AZURE_CLAUDE_DEPLOYMENT", "claude-opus-4-6")


def analyze(system_prompt: str, user_prompt: str) -> str:
    last_err = None
    for attempt in range(3):
        try:
            message = _client.messages.create(
                model=_MODEL,
                max_tokens=16000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return message.content[0].text.strip()
        except Exception as e:
            last_err = e
            wait = 10 * (2 ** attempt)
            print(f"  [retry {attempt + 1}/3] Azure error: {e} — waiting {wait}s")
            time.sleep(wait)
    raise last_err
