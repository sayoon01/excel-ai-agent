"""Multi-provider LLM client: Ollama, Gemini, OpenAI."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generator


class LLMClient(ABC):
    @abstractmethod
    def chat_stream(
        self, messages: list[dict], system_prompt: str
    ) -> Generator[str, None, None]:
        pass


# ── Ollama ─────────────────────────────────────────────────────────────────────

class OllamaClient(LLMClient):
    def __init__(self, host: str = "http://localhost:11434", model: str = ""):
        import ollama
        self._client = ollama.Client(host=host)
        self._model = model
        self.temperature: float = 0.7
        self.num_predict: int = 4096

    def chat_stream(
        self, messages: list[dict], system_prompt: str
    ) -> Generator[str, None, None]:
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        stream = self._client.chat(
            model=self._model,
            messages=full_messages,
            stream=True,
            options={"temperature": self.temperature, "num_predict": self.num_predict},
        )
        for chunk in stream:
            token = chunk.message.content
            if token:
                yield token

    def with_model(self, model: str) -> "OllamaClient":
        self._model = model
        return self


def list_ollama_models(host: str = "http://localhost:11434") -> list[str]:
    try:
        import ollama
        client = ollama.Client(host=host)
        response = client.list()
        return [m.model for m in response.models]
    except Exception:
        return []


# ── Gemini ─────────────────────────────────────────────────────────────────────

class GeminiClient(LLMClient):
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._genai = genai
        self._model_name = model
        self.temperature: float = 0.7
        self.max_output_tokens: int = 4096

    def chat_stream(
        self, messages: list[dict], system_prompt: str
    ) -> Generator[str, None, None]:
        import google.generativeai as genai
        config = genai.types.GenerationConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
        )
        model = self._genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=system_prompt,
            generation_config=config,
        )
        history = []
        for msg in messages[:-1]:
            role = "model" if msg["role"] == "assistant" else "user"
            history.append({"role": role, "parts": [msg["content"]]})

        chat = model.start_chat(history=history)
        last_user = messages[-1]["content"]
        response = chat.send_message(last_user, stream=True)
        for chunk in response:
            if chunk.text:
                yield chunk.text


GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash-thinking-exp",
]


# ── OpenAI ─────────────────────────────────────────────────────────────────────

class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key)
        self._model = model
        self.temperature: float = 0.7
        self.max_tokens: int = 4096

    def chat_stream(
        self, messages: list[dict], system_prompt: str
    ) -> Generator[str, None, None]:
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        stream = self._client.chat.completions.create(
            model=self._model,
            messages=full_messages,
            stream=True,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-3.5-turbo",
]


# ── Factory ────────────────────────────────────────────────────────────────────

def get_client(
    provider: str,
    model: str,
    api_key: str = "",
    ollama_host: str = "http://localhost:11434",
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> LLMClient | None:
    try:
        if provider == "Ollama":
            c = OllamaClient(host=ollama_host, model=model)
            c.temperature = temperature
            c.num_predict = max_tokens
            return c
        elif provider == "Gemini":
            c = GeminiClient(api_key=api_key, model=model)
            c.temperature = temperature
            c.max_output_tokens = max_tokens
            return c
        elif provider == "OpenAI":
            c = OpenAIClient(api_key=api_key, model=model)
            c.temperature = temperature
            c.max_tokens = max_tokens
            return c
    except Exception:
        return None
    return None
