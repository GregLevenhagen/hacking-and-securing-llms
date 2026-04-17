"""Tests for the response_constrainer validator module."""

from validators import response_constrainer


class TestResponseConstrainerCheck:
    """Tests for response_constrainer.check()."""

    def test_response_exceeding_max_length_flagged(self) -> None:
        output = "x" * 2500
        result = response_constrainer.check(output)
        assert result["valid"] is False
        assert any("exceeds maximum" in v for v in result["violations"])
        assert result["validator"] == "response_constrainer"

    def test_response_at_max_length_passes(self) -> None:
        output = "x" * 2000
        result = response_constrainer.check(output)
        # Check no length violation (topic violations are separate)
        length_violations = [v for v in result["violations"] if "exceeds" in v]
        assert len(length_violations) == 0

    def test_custom_max_length(self) -> None:
        output = "x" * 150
        result = response_constrainer.check(output, max_length=100)
        assert result["valid"] is False
        assert any("exceeds maximum 100" in v for v in result["violations"])

    def test_short_response_passes_custom_length(self) -> None:
        output = "Short response"
        result = response_constrainer.check(output, max_length=100)
        assert result["valid"] is True

    def test_competitor_openai_flagged(self) -> None:
        output = "I recommend using ChatGPT for your tasks."
        result = response_constrainer.check(output)
        assert result["valid"] is False
        assert any("OpenAI" in v for v in result["violations"])

    def test_competitor_google_flagged(self) -> None:
        output = "Google Gemini Pro is a powerful alternative."
        result = response_constrainer.check(output)
        assert result["valid"] is False
        assert any("Google AI" in v for v in result["violations"])

    def test_competitor_anthropic_flagged(self) -> None:
        output = "Anthropic has released Claude Opus recently."
        result = response_constrainer.check(output)
        assert result["valid"] is False
        assert any("Anthropic" in v for v in result["violations"])

    def test_internal_project_flagged(self) -> None:
        output = "Our Project Phoenix initiative will launch next quarter."
        result = response_constrainer.check(output)
        assert result["valid"] is False
        assert any("Internal project" in v for v in result["violations"])

    def test_normal_on_topic_response_passes(self) -> None:
        output = "Our product offers excellent performance and reliability."
        result = response_constrainer.check(output)
        assert result["valid"] is True
        assert result["violations"] == []
        assert result["validator"] == "response_constrainer"

    def test_multiple_violations(self) -> None:
        # Both too long and mentions competitor
        output = "ChatGPT is great. " + "x" * 2000
        result = response_constrainer.check(output)
        assert result["valid"] is False
        assert len(result["violations"]) >= 2

    def test_empty_output_passes(self) -> None:
        result = response_constrainer.check("")
        assert result["valid"] is True
        assert result["violations"] == []

    def test_case_insensitive_competitor_detection(self) -> None:
        output = "Have you tried OPENAI or chatgpt?"
        result = response_constrainer.check(output)
        assert result["valid"] is False

    def test_custom_restricted_topics(self) -> None:
        custom_topics = [
            {
                "name": "forbidden_word",
                "pattern": r"\bforbidden\b",
                "description": "Forbidden word",
            }
        ]
        output = "This contains a forbidden word."
        result = response_constrainer.check(
            output, restricted_topics=custom_topics
        )
        assert result["valid"] is False
        assert any("Forbidden word" in v for v in result["violations"])

    def test_custom_topics_override_defaults(self) -> None:
        # With custom topics, default competitors should NOT be flagged
        custom_topics = [
            {
                "name": "test",
                "pattern": r"\btest_only\b",
                "description": "Test pattern",
            }
        ]
        output = "ChatGPT is great but no test_only here."
        result = response_constrainer.check(
            output, restricted_topics=custom_topics
        )
        # ChatGPT should pass since we overrode the default topics
        topic_violations = [v for v in result["violations"] if "OpenAI" in v]
        assert len(topic_violations) == 0


class TestGetRestrictedTopics:
    """Tests for response_constrainer.get_restricted_topics()."""

    def test_returns_list(self) -> None:
        topics = response_constrainer.get_restricted_topics()
        assert isinstance(topics, list)
        assert len(topics) > 0

    def test_each_topic_has_required_fields(self) -> None:
        for t in response_constrainer.get_restricted_topics():
            assert "name" in t
            assert "pattern" in t
            assert "description" in t
