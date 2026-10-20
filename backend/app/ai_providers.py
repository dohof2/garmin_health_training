from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from openai import OpenAI

from .database import connect, migrate


AI_PROVIDERS = {"ollama", "openai", "chatgpt"}
OLLAMA_BASE_URL = "http://127.0.0.1:11434"


class AIProvider(Protocol):
    def generate(self, prompt: str, instructions: str, *, timeout_seconds: float = 120) -> str: ...


def _model_name(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    if len(text) > 100:
        raise ValueError(f"{field} must be 100 characters or fewer")
    if any(character.isspace() for character in text):
        raise ValueError(f"{field} cannot contain spaces")
    return text


def get_ai_settings(path: Path | None = None) -> dict[str, object]:
    migrate(path)
    with connect(path) as connection:
        row = connection.execute(
            """
            SELECT active_provider, ollama_model, openai_model, chatgpt_model, updated_at
            FROM ai_settings WHERE id = 1
            """
        ).fetchone()
    if row is None:
        raise RuntimeError("AI settings are missing")
    return dict(row)


def save_ai_settings(
    settings: dict[str, object], path: Path | None = None
) -> dict[str, object]:
    provider = str(settings.get("active_provider") or "").strip().lower()
    if provider not in AI_PROVIDERS:
        raise ValueError("active_provider must be ollama, openai or chatgpt")
    ollama_model = _model_name(settings.get("ollama_model"), "ollama_model")
    openai_model = _model_name(settings.get("openai_model"), "openai_model")

    chatgpt_model = str(settings.get("chatgpt_model") or "").strip()
    if chatgpt_model: chatgpt_model = _model_name(chatgpt_model,"chatgpt_model")
    migrate(path)
    with connect(path) as connection:
        connection.execute(
            """
            UPDATE ai_settings
            SET active_provider = ?, ollama_model = ?, openai_model = ?, chatgpt_model = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            (provider, ollama_model, openai_model, chatgpt_model),
        )
    return get_ai_settings(path)


def _ollama_models(timeout_seconds: float = 1.5) -> set[str]:
    request = Request(f"{OLLAMA_BASE_URL}/api/tags", method="GET")
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return {
        str(model.get("name") or model.get("model"))
        for model in payload.get("models", [])
        if model.get("name") or model.get("model")
    }


def provider_status(path: Path | None = None) -> dict[str, object]:
    settings = get_ai_settings(path)
    ollama_model = str(settings["ollama_model"])
    try:
        installed_models = _ollama_models()
        ollama_ready = ollama_model in installed_models
        ollama_detail = (
            "Local model is installed and Ollama is reachable."
            if ollama_ready
            else "Ollama is reachable, but the selected model is not installed."
        )
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        ollama_ready = False
        ollama_detail = "Ollama is not reachable on this computer."

    from .chatgpt_auth import status
    chatgpt = status(path)
    openai_configured = bool(os.getenv("OPENAI_API_KEY", "").strip())
    return {
        "active_provider": settings["active_provider"],
        "chatgpt": chatgpt,
        "providers": {
            "chatgpt": {"configured":chatgpt["connected"],"available":chatgpt["connected"] and bool(settings["chatgpt_model"]),"model":settings["chatgpt_model"],"detail":chatgpt["detail"]},
            "ollama": {
                "configured": True,
                "available": ollama_ready,
                "model": ollama_model,
                "detail": ollama_detail,
            },
            "openai": {
                "configured": openai_configured,
                "available": openai_configured,
                "model": settings["openai_model"],
                "detail": (
                    "API key detected; access will be verified on the first request."
                    if openai_configured
                    else "Set OPENAI_API_KEY in the backend environment."
                ),
            },
        },
    }


class OllamaProvider:
    def __init__(self, model: str) -> None:
        self.model = model

    def generate(self, prompt: str, instructions: str, *, timeout_seconds: float = 120) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": prompt},
                ],
            }
        ).encode("utf-8")
        request = Request(
            f"{OLLAMA_BASE_URL}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return str(payload["message"]["content"])


class OpenAIProvider:
    def __init__(self, model: str) -> None:
        if not os.getenv("OPENAI_API_KEY", "").strip():
            raise RuntimeError("OPENAI_API_KEY is not configured")
        self.model = model

    def generate(self, prompt: str, instructions: str, *, timeout_seconds: float = 120) -> str:
        response = OpenAI(timeout=timeout_seconds, max_retries=0).responses.create(
            model=self.model,
            instructions=instructions,
            input=prompt,
            store=False,
        )
        return response.output_text


def active_provider(path: Path | None = None) -> AIProvider:
    settings = get_ai_settings(path)
    if settings["active_provider"] == "chatgpt":
        return ChatGPTProvider(str(settings["chatgpt_model"]),path)
    if settings["active_provider"] == "openai":
        return OpenAIProvider(str(settings["openai_model"]))
    return OllamaProvider(str(settings["ollama_model"]))


class ChatGPTProvider:
    def __init__(self,model,path=None):self.model=model;self.path=path
    def generate(self,prompt,instructions,*,timeout_seconds=120):
        from .chatgpt_auth import access_token
        if not self.model:raise RuntimeError('Select a ChatGPT model in Settings.')
        client=OpenAI(api_key=access_token(self.path),base_url='https://api.openai.com/v1',timeout=timeout_seconds,max_retries=0)
        text=[];completed=False
        reasoning = {'reasoning': {'effort': 'low'}} if '-sol' in self.model else {}
        for event in client.responses.create(model=self.model,instructions=instructions,input=[{'role':'user','content':prompt}],store=False,stream=True,**reasoning):
            if event.type=='response.output_text.delta':text.append(event.delta)
            elif event.type=='response.completed':completed=True
            elif event.type in {'response.failed','response.incomplete','error'}:raise RuntimeError('ChatGPT request failed or was incomplete. Check account access and usage in Settings.')
        if not completed:raise RuntimeError('ChatGPT stream ended before completion.')
        return ''.join(text)
