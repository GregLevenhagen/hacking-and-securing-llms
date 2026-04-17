"""Unit tests for shared/python/ollama_client.py and config.py.

All tests mock the OpenAI SDK — no running Ollama instance required.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from shared.python.config import Config, ConfigError, get_config, reset_config
from shared.python.ollama_client import OllamaClient, OllamaClientError


# ── Config tests ─────────────────────────────────────────────────────


class TestConfigDefaults:
    def test_defaults_without_env(self) -> None:
        config = Config()
        assert config.ollama_base_url == "http://localhost:11434/v1"
        assert config.primary_model == "llama3.1:8b"
        assert config.secondary_model == "mistral:7b"
        assert config.embedding_model == "nomic-embed-text"
        assert config.temperature == 0.7

    def test_load_from_environment(self) -> None:
        env = {
            "OLLAMA_BASE_URL": "http://custom:9999/v1",
            "PRIMARY_MODEL": "custom-model",
            "SECONDARY_MODEL": "custom-secondary",
            "EMBEDDING_MODEL": "custom-embed",
            "TEMPERATURE": "0.3",
        }
        with patch.dict(os.environ, env, clear=False):
            config = Config.load()

        assert config.ollama_base_url == "http://custom:9999/v1"
        assert config.primary_model == "custom-model"
        assert config.secondary_model == "custom-secondary"
        assert config.embedding_model == "custom-embed"
        assert config.temperature == 0.3

    def test_get_config_returns_singleton(self) -> None:
        reset_config()
        c1 = get_config()
        c2 = get_config()
        assert c1 is c2
        reset_config()

    def test_reset_config_clears_singleton(self) -> None:
        reset_config()
        c1 = get_config()
        reset_config()
        c2 = get_config()
        assert c1 is not c2
        reset_config()


class TestConfigValidation:
    def test_empty_url_raises(self) -> None:
        with pytest.raises(ConfigError, match="ollama_base_url must not be empty"):
            Config(ollama_base_url="")

    def test_invalid_url_scheme_raises(self) -> None:
        with pytest.raises(ConfigError, match="must start with http://"):
            Config(ollama_base_url="ftp://localhost:11434/v1")

    def test_https_url_is_valid(self) -> None:
        config = Config(ollama_base_url="https://api.example.com/v1")
        assert config.ollama_base_url == "https://api.example.com/v1"

    def test_empty_primary_model_raises(self) -> None:
        with pytest.raises(ConfigError, match="primary_model must not be empty"):
            Config(primary_model="")

    def test_empty_secondary_model_raises(self) -> None:
        with pytest.raises(ConfigError, match="secondary_model must not be empty"):
            Config(secondary_model="")

    def test_empty_embedding_model_raises(self) -> None:
        with pytest.raises(ConfigError, match="embedding_model must not be empty"):
            Config(embedding_model="")

    def test_temperature_below_zero_raises(self) -> None:
        with pytest.raises(ConfigError, match="temperature must be between"):
            Config(temperature=-0.1)

    def test_temperature_above_two_raises(self) -> None:
        with pytest.raises(ConfigError, match="temperature must be between"):
            Config(temperature=2.1)

    def test_temperature_boundary_zero_is_valid(self) -> None:
        config = Config(temperature=0.0)
        assert config.temperature == 0.0

    def test_temperature_boundary_two_is_valid(self) -> None:
        config = Config(temperature=2.0)
        assert config.temperature == 2.0

    def test_invalid_temperature_string_in_env_raises(self) -> None:
        env = {"TEMPERATURE": "not_a_number"}
        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ConfigError, match="TEMPERATURE must be a valid float"):
                Config.load()


# ── OllamaClient.chat() tests ───────────────────────────────────────


class TestChat:
    def setup_method(self) -> None:
        self.config = Config(
            ollama_base_url="http://localhost:11434/v1",
            primary_model="test-model",
            temperature=0.0,
        )

    @patch("shared.python.ollama_client.OpenAI")
    def test_chat_returns_content_string(self, mock_openai_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello world"
        mock_client.chat.completions.create.return_value = mock_response

        client = OllamaClient(config=self.config)
        result = client.chat([{"role": "user", "content": "Hi"}])

        assert result == "Hello world"
        mock_client.chat.completions.create.assert_called_once()

    @patch("shared.python.ollama_client.OpenAI")
    def test_chat_passes_correct_model(self, mock_openai_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"
        mock_client.chat.completions.create.return_value = mock_response

        client = OllamaClient(config=self.config)
        client.chat([{"role": "user", "content": "test"}])

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "test-model"

    @patch("shared.python.ollama_client.OpenAI")
    def test_chat_uses_custom_model(self, mock_openai_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "ok"
        mock_client.chat.completions.create.return_value = mock_response

        client = OllamaClient(config=self.config)
        client.chat([{"role": "user", "content": "test"}], model="custom-model")

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "custom-model"

    @patch("shared.python.ollama_client.OpenAI")
    def test_chat_with_tools_returns_full_response(
        self, mock_openai_cls: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.tool_calls = [MagicMock()]
        mock_client.chat.completions.create.return_value = mock_response

        tools = [{"type": "function", "function": {"name": "test", "parameters": {}}}]

        client = OllamaClient(config=self.config)
        result = client.chat(
            [{"role": "user", "content": "call tool"}], tools=tools
        )

        # With tools, should return the full response object
        assert result is mock_response

    @patch("shared.python.ollama_client.OpenAI")
    def test_chat_sends_tools_to_api(self, mock_openai_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        tools = [{"type": "function", "function": {"name": "calc", "parameters": {}}}]

        client = OllamaClient(config=self.config)
        client.chat([{"role": "user", "content": "calc"}], tools=tools)

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["tools"] == tools

    @patch("shared.python.ollama_client.OpenAI")
    def test_chat_empty_content_returns_empty_string(
        self, mock_openai_cls: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_client.chat.completions.create.return_value = mock_response

        client = OllamaClient(config=self.config)
        result = client.chat([{"role": "user", "content": "Hi"}])
        assert result == ""


# ── OllamaClient.chat_stream() tests ────────────────────────────────


class TestChatStream:
    def setup_method(self) -> None:
        self.config = Config(
            ollama_base_url="http://localhost:11434/v1",
            primary_model="test-model",
            temperature=0.0,
        )

    @patch("shared.python.ollama_client.OpenAI")
    def test_chat_stream_yields_tokens(self, mock_openai_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        # Simulate streaming chunks
        chunks = []
        for token in ["Hello", " ", "world"]:
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = token
            chunks.append(chunk)

        mock_client.chat.completions.create.return_value = iter(chunks)

        client = OllamaClient(config=self.config)
        tokens = list(
            client.chat_stream([{"role": "user", "content": "Hi"}])
        )

        assert tokens == ["Hello", " ", "world"]

    @patch("shared.python.ollama_client.OpenAI")
    def test_chat_stream_passes_stream_flag(
        self, mock_openai_cls: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = iter([])

        client = OllamaClient(config=self.config)
        list(client.chat_stream([{"role": "user", "content": "Hi"}]))

        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["stream"] is True

    @patch("shared.python.ollama_client.OpenAI")
    def test_chat_stream_skips_empty_chunks(
        self, mock_openai_cls: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        empty_chunk = MagicMock()
        empty_chunk.choices = [MagicMock()]
        empty_chunk.choices[0].delta.content = None

        content_chunk = MagicMock()
        content_chunk.choices = [MagicMock()]
        content_chunk.choices[0].delta.content = "data"

        no_choices_chunk = MagicMock()
        no_choices_chunk.choices = []

        mock_client.chat.completions.create.return_value = iter(
            [empty_chunk, no_choices_chunk, content_chunk]
        )

        client = OllamaClient(config=self.config)
        tokens = list(
            client.chat_stream([{"role": "user", "content": "Hi"}])
        )
        assert tokens == ["data"]


# ── OllamaClient.embed() tests ──────────────────────────────────────


class TestEmbed:
    def setup_method(self) -> None:
        self.config = Config(
            ollama_base_url="http://localhost:11434/v1",
            embedding_model="nomic-embed-text",
        )

    @patch("shared.python.ollama_client.OpenAI")
    def test_embed_returns_vector(self, mock_openai_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        expected_vector = [0.1] * 384
        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].embedding = expected_vector
        mock_client.embeddings.create.return_value = mock_response

        client = OllamaClient(config=self.config)
        vector = client.embed("test text")

        assert vector == expected_vector
        assert len(vector) == 384

    @patch("shared.python.ollama_client.OpenAI")
    def test_embed_uses_default_model(self, mock_openai_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].embedding = [0.0]
        mock_client.embeddings.create.return_value = mock_response

        client = OllamaClient(config=self.config)
        client.embed("test")

        call_kwargs = mock_client.embeddings.create.call_args
        assert call_kwargs.kwargs["model"] == "nomic-embed-text"

    @patch("shared.python.ollama_client.OpenAI")
    def test_embed_uses_custom_model(self, mock_openai_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].embedding = [0.0]
        mock_client.embeddings.create.return_value = mock_response

        client = OllamaClient(config=self.config)
        client.embed("test", model="custom-embed")

        call_kwargs = mock_client.embeddings.create.call_args
        assert call_kwargs.kwargs["model"] == "custom-embed"


# ── OllamaClient error handling tests ────────────────────────────────


class TestClientErrorHandling:
    """Verify OllamaClient wraps API errors in OllamaClientError."""

    def setup_method(self) -> None:
        self.config = Config(
            ollama_base_url="http://localhost:11434/v1",
            primary_model="test-model",
            temperature=0.0,
        )

    @patch("shared.python.ollama_client.OpenAI")
    def test_chat_connection_error(self, mock_openai_cls: MagicMock) -> None:
        from openai import APIConnectionError

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = APIConnectionError(
            request=MagicMock()
        )

        client = OllamaClient(config=self.config)
        with pytest.raises(OllamaClientError, match="Cannot connect to Ollama"):
            client.chat([{"role": "user", "content": "Hi"}])

    @patch("shared.python.ollama_client.OpenAI")
    def test_chat_api_status_error(self, mock_openai_cls: MagicMock) -> None:
        from openai import APIStatusError

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        err = APIStatusError(
            message="model not found",
            response=MagicMock(status_code=404),
            body=None,
        )
        mock_client.chat.completions.create.side_effect = err

        client = OllamaClient(config=self.config)
        with pytest.raises(OllamaClientError, match="Ollama API error"):
            client.chat([{"role": "user", "content": "Hi"}])

    @patch("shared.python.ollama_client.OpenAI")
    def test_chat_stream_connection_error(self, mock_openai_cls: MagicMock) -> None:
        from openai import APIConnectionError

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.side_effect = APIConnectionError(
            request=MagicMock()
        )

        client = OllamaClient(config=self.config)
        with pytest.raises(OllamaClientError, match="Cannot connect to Ollama"):
            list(client.chat_stream([{"role": "user", "content": "Hi"}]))

    @patch("shared.python.ollama_client.OpenAI")
    def test_embed_connection_error(self, mock_openai_cls: MagicMock) -> None:
        from openai import APIConnectionError

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.embeddings.create.side_effect = APIConnectionError(
            request=MagicMock()
        )

        client = OllamaClient(config=self.config)
        with pytest.raises(OllamaClientError, match="Cannot connect to Ollama"):
            client.embed("test text")

    @patch("shared.python.ollama_client.OpenAI")
    def test_error_preserves_cause(self, mock_openai_cls: MagicMock) -> None:
        from openai import APIConnectionError

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        original_error = APIConnectionError(request=MagicMock())
        mock_client.chat.completions.create.side_effect = original_error

        client = OllamaClient(config=self.config)
        with pytest.raises(OllamaClientError) as exc_info:
            client.chat([{"role": "user", "content": "Hi"}])
        assert exc_info.value.cause is original_error


# ── MockOllamaClient tests ──────────────────────────────────────────


class TestMockOllamaClient:
    """Verify the mock itself works correctly so demos can rely on it."""

    def test_default_response(self) -> None:
        from shared.python.testing.mock_ollama import MockOllamaClient

        client = MockOllamaClient()
        result = client.chat([{"role": "user", "content": "anything"}])
        assert result == "This is a mock response."

    def test_pattern_matching(self) -> None:
        from shared.python.testing.mock_ollama import MockOllamaClient

        client = MockOllamaClient(
            responses={"hello": "Hi there!", "translate": "Bonjour"}
        )
        result = client.chat([{"role": "user", "content": "hello world"}])
        assert result == "Hi there!"

    def test_stream_yields_tokens(self) -> None:
        from shared.python.testing.mock_ollama import MockOllamaClient

        client = MockOllamaClient(default_response="one two three")
        tokens = list(
            client.chat_stream([{"role": "user", "content": "test"}])
        )
        assert "".join(tokens) == "one two three"

    def test_embed_returns_correct_dimension(self) -> None:
        from shared.python.testing.mock_ollama import MockOllamaClient

        client = MockOllamaClient()
        vector = client.embed("test text")
        assert len(vector) == 384

    def test_call_history_tracked(self) -> None:
        from shared.python.testing.mock_ollama import MockOllamaClient

        client = MockOllamaClient()
        client.chat([{"role": "user", "content": "msg1"}])
        client.embed("text1")
        assert len(client.call_history) == 2
        assert client.call_history[0]["method"] == "chat"
        assert client.call_history[1]["method"] == "embed"

    def test_tool_call_response(self) -> None:
        from shared.python.testing.mock_ollama import MockOllamaClient

        client = MockOllamaClient(
            tool_call_responses=[
                {
                    "function": {
                        "name": "calculate",
                        "arguments": '{"expression": "2+2"}',
                    }
                }
            ]
        )
        tools = [{"type": "function", "function": {"name": "calculate", "parameters": {}}}]
        result = client.chat(
            [{"role": "user", "content": "calc 2+2"}], tools=tools
        )

        # With tools, returns full response object
        assert hasattr(result, "choices")
        tc = result.choices[0].message.tool_calls
        assert tc is not None
        assert tc[0].function.name == "calculate"

    def test_reset_call_history(self) -> None:
        from shared.python.testing.mock_ollama import MockOllamaClient

        client = MockOllamaClient()
        client.chat([{"role": "user", "content": "msg1"}])
        assert len(client.call_history) == 1
        client.reset_call_history()
        assert len(client.call_history) == 0

    def test_last_call_property(self) -> None:
        from shared.python.testing.mock_ollama import MockOllamaClient

        client = MockOllamaClient()
        assert client.last_call is None
        client.chat([{"role": "user", "content": "first"}])
        client.embed("second")
        assert client.last_call is not None
        assert client.last_call["method"] == "embed"

    def test_chat_calls_filter(self) -> None:
        from shared.python.testing.mock_ollama import MockOllamaClient

        client = MockOllamaClient()
        client.chat([{"role": "user", "content": "msg1"}])
        client.embed("text1")
        client.chat([{"role": "user", "content": "msg2"}])
        assert len(client.chat_calls) == 2
        assert len(client.embed_calls) == 1

    def test_tool_call_ids_are_unique(self) -> None:
        from shared.python.testing.mock_ollama import MockOllamaClient

        client = MockOllamaClient(
            tool_call_responses=[
                {"function": {"name": "tool_a", "arguments": "{}"}},
                {"function": {"name": "tool_b", "arguments": "{}"}},
            ]
        )
        tools = [{"type": "function", "function": {"name": "t", "parameters": {}}}]
        result = client.chat([{"role": "user", "content": "go"}], tools=tools)
        tc = result.choices[0].message.tool_calls
        assert tc is not None
        assert len(tc) == 2
        assert tc[0].id != tc[1].id  # IDs should be unique

    def test_embed_returns_copy_not_reference(self) -> None:
        from shared.python.testing.mock_ollama import MockOllamaClient

        client = MockOllamaClient()
        v1 = client.embed("test")
        v2 = client.embed("test")
        assert v1 == v2
        assert v1 is not v2  # Should return a copy each time

    def test_embed_many_returns_multiple_vectors(self) -> None:
        from shared.python.testing.mock_ollama import MockOllamaClient

        client = MockOllamaClient()
        results = client.embed_many(["text1", "text2", "text3"])
        assert len(results) == 3
        for vec in results:
            assert len(vec) == 384

    def test_embed_many_empty_input(self) -> None:
        from shared.python.testing.mock_ollama import MockOllamaClient

        client = MockOllamaClient()
        results = client.embed_many([])
        assert results == []

    def test_health_check_returns_true(self) -> None:
        from shared.python.testing.mock_ollama import MockOllamaClient

        client = MockOllamaClient()
        assert client.health_check() is True
        assert client.call_history[-1]["method"] == "health_check"


# ── SequencedMockClient tests ────────────────────────────────────────


class TestSequencedMockClient:
    """Verify SequencedMockClient returns responses in order and handles exhaustion."""

    def test_returns_responses_in_sequence(self) -> None:
        from shared.python.testing.mock_ollama import SequencedMockClient

        client = SequencedMockClient(
            response_sequence=[
                ("First response", None),
                ("Second response", None),
            ]
        )
        r1 = client.chat([{"role": "user", "content": "q1"}])
        r2 = client.chat([{"role": "user", "content": "q2"}])

        assert r1.choices[0].message.content == "First response"
        assert r2.choices[0].message.content == "Second response"

    def test_returns_tool_calls_when_provided(self) -> None:
        from shared.python.testing.mock_ollama import SequencedMockClient

        client = SequencedMockClient(
            response_sequence=[
                (
                    "Calling tool",
                    [{"name": "calculate", "arguments": '{"expr": "2+2"}'}],
                ),
                ("Final answer: 4", None),
            ]
        )
        r1 = client.chat(
            [{"role": "user", "content": "calc"}],
            tools=[{"type": "function", "function": {"name": "calculate"}}],
        )
        r2 = client.chat([{"role": "user", "content": "result"}])

        assert r1.choices[0].message.tool_calls is not None
        assert r1.choices[0].message.tool_calls[0].function.name == "calculate"
        assert r2.choices[0].message.tool_calls is None

    def test_returns_fallback_after_exhaustion(self) -> None:
        from shared.python.testing.mock_ollama import SequencedMockClient

        client = SequencedMockClient(
            response_sequence=[("Only one", None)],
            fallback="Exhausted.",
        )
        client.chat([{"role": "user", "content": "first"}])
        r2 = client.chat([{"role": "user", "content": "second"}])

        assert r2.choices[0].message.content == "Exhausted."
        assert r2.choices[0].message.tool_calls is None

    def test_call_count_increments(self) -> None:
        from shared.python.testing.mock_ollama import SequencedMockClient

        client = SequencedMockClient(
            response_sequence=[("a", None), ("b", None)]
        )
        assert client.call_count == 0
        client.chat([{"role": "user", "content": "q1"}])
        assert client.call_count == 1
        client.chat([{"role": "user", "content": "q2"}])
        assert client.call_count == 2
        # Past exhaustion
        client.chat([{"role": "user", "content": "q3"}])
        assert client.call_count == 3

    def test_call_history_recorded(self) -> None:
        from shared.python.testing.mock_ollama import SequencedMockClient

        client = SequencedMockClient(
            response_sequence=[("resp", None)]
        )
        msgs: list[dict[str, str]] = [{"role": "user", "content": "test"}]
        client.chat(msgs, model="test-model", tools=None)  # type: ignore[arg-type]

        assert len(client.call_history) == 1
        assert client.call_history[0]["messages"] == msgs
        assert client.call_history[0]["model"] == "test-model"

    def test_empty_sequence_returns_fallback_immediately(self) -> None:
        from shared.python.testing.mock_ollama import SequencedMockClient

        client = SequencedMockClient(fallback="No sequence.")
        r = client.chat([{"role": "user", "content": "q"}])
        assert r.choices[0].message.content == "No sequence."

    def test_multiple_tool_calls_in_single_step(self) -> None:
        from shared.python.testing.mock_ollama import SequencedMockClient

        client = SequencedMockClient(
            response_sequence=[
                (
                    "Calling two tools",
                    [
                        {"name": "read_file", "arguments": '{"path": "a.txt"}'},
                        {"name": "query_db", "arguments": '{"sql": "SELECT 1"}'},
                    ],
                ),
            ]
        )
        r = client.chat(
            [{"role": "user", "content": "do both"}],
            tools=[{"type": "function", "function": {"name": "t"}}],
        )
        tc = r.choices[0].message.tool_calls
        assert tc is not None
        assert len(tc) == 2
        assert tc[0].function.name == "read_file"
        assert tc[1].function.name == "query_db"
        # IDs should be unique
        assert tc[0].id != tc[1].id


class TestEmbedMany:
    """Tests for embed_many() — batch embedding via the OpenAI API."""

    def setup_method(self) -> None:
        self.config = Config(
            ollama_base_url="http://localhost:11434/v1",
            embedding_model="nomic-embed-text",
        )

    @patch("shared.python.ollama_client.OpenAI")
    def test_embed_many_returns_vectors(self, mock_openai_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=[0.1] * 384),
            MagicMock(embedding=[0.2] * 384),
        ]
        mock_client.embeddings.create.return_value = mock_response

        client = OllamaClient(config=self.config)
        result = client.embed_many(["text1", "text2"])

        assert len(result) == 2
        assert result[0] == [0.1] * 384
        assert result[1] == [0.2] * 384

    @patch("shared.python.ollama_client.OpenAI")
    def test_embed_many_empty_returns_empty(self, mock_openai_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        client = OllamaClient(config=self.config)
        result = client.embed_many([])

        assert result == []
        mock_client.embeddings.create.assert_not_called()


class TestHealthCheck:
    """Tests for health_check() — Ollama connectivity verification."""

    def setup_method(self) -> None:
        self.config = Config(
            ollama_base_url="http://localhost:11434/v1",
        )

    @patch("shared.python.ollama_client.OpenAI")
    def test_health_check_returns_true_when_connected(self, mock_openai_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.models.list.return_value = MagicMock()

        client = OllamaClient(config=self.config)
        assert client.health_check() is True

    @patch("shared.python.ollama_client.OpenAI")
    def test_health_check_returns_false_on_connection_error(self, mock_openai_cls: MagicMock) -> None:
        from openai import APIConnectionError

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.models.list.side_effect = APIConnectionError(request=MagicMock())

        client = OllamaClient(config=self.config)
        assert client.health_check() is False
