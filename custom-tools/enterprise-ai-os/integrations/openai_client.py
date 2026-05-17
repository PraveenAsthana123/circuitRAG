import os
from typing import Dict, Any, List
from openai import OpenAI


class OpenAIClient:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.default_model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str | None = None,
        temperature: float = 0.0
    ) -> Dict[str, Any]:

        response = self.client.chat.completions.create(
            model=model or self.default_model,
            messages=messages,
            temperature=temperature
        )

        return {
            "provider": "openai",
            "model": model or self.default_model,
            "text": response.choices[0].message.content,
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens
        }
