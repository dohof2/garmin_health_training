from __future__ import annotations

import json
import tempfile
import unittest
from os import environ
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.ai_providers import OllamaProvider, OpenAIProvider, active_provider, save_ai_settings


class AIProviderTests(unittest.TestCase):
    @patch("app.ai_providers.urlopen")
    def test_ollama_provider_uses_only_the_local_chat_endpoint(self, urlopen: MagicMock) -> None:
        response = MagicMock()
        response.read.return_value = json.dumps(
            {"message": {"content": "Local answer"}}
        ).encode("utf-8")
        urlopen.return_value.__enter__.return_value = response

        result = OllamaProvider("qwen3.5:2b").generate("Question", "Rules")

        self.assertEqual(result, "Local answer")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "qwen3.5:2b")
        self.assertFalse(payload["stream"])

    @patch("app.ai_providers.OpenAI")
    def test_openai_provider_uses_responses_api_without_server_storage(
        self, openai_client: MagicMock
    ) -> None:
        openai_client.return_value.responses.create.return_value.output_text = "Cloud answer"
        with patch.dict(environ, {"OPENAI_API_KEY": "secret-test-key"}):
            result = OpenAIProvider("gpt-6-astra").generate("Question", "Rules")

        self.assertEqual(result, "Cloud answer")
        openai_client.return_value.responses.create.assert_called_once_with(
            model="gpt-6-astra",
            instructions="Rules",
            input="Question",
            store=False,
        )

    def test_active_provider_follows_saved_manual_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "settings.sqlite3"
            save_ai_settings(
                {
                    "active_provider": "openai",
                    "ollama_model": "qwen3.5:2b",
                    "openai_model": "gpt-6-astra",
                },
                database,
            )
            with patch.dict(environ, {"OPENAI_API_KEY": "secret-test-key"}):
                provider = active_provider(database)
            self.assertIsInstance(provider, OpenAIProvider)


if __name__ == "__main__":
    unittest.main()
