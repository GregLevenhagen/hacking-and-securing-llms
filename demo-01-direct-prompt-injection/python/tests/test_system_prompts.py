"""Tests for system_prompts.py — verifies prompt loading and structure."""

from system_prompts import PROMPTS, get_all_prompts, get_prompt_by_name, get_prompt_names


class TestPromptsStructure:
    """Verify the PROMPTS list has the expected shape and content."""

    def test_prompt_count(self) -> None:
        """There should be 3–4 system prompts of increasing strictness."""
        assert 3 <= len(PROMPTS) <= 4

    def test_each_prompt_is_dict_with_required_keys(self) -> None:
        for p in PROMPTS:
            assert isinstance(p, dict)
            assert "name" in p
            assert "prompt" in p

    def test_each_prompt_text_is_nonempty_string(self) -> None:
        for p in PROMPTS:
            assert isinstance(p["prompt"], str)
            assert len(p["prompt"].strip()) > 0

    def test_each_name_is_nonempty_string(self) -> None:
        for p in PROMPTS:
            assert isinstance(p["name"], str)
            assert len(p["name"].strip()) > 0

    def test_names_are_unique(self) -> None:
        names = [p["name"] for p in PROMPTS]
        assert len(names) == len(set(names))


class TestGetPromptNames:
    def test_returns_list_of_strings(self) -> None:
        names = get_prompt_names()
        assert isinstance(names, list)
        assert all(isinstance(n, str) for n in names)

    def test_count_matches_prompts(self) -> None:
        assert len(get_prompt_names()) == len(PROMPTS)


class TestGetPromptByName:
    def test_valid_name_returns_prompt(self) -> None:
        prompt = get_prompt_by_name("Basic Instruction")
        assert prompt is not None
        assert "French" in prompt

    def test_invalid_name_returns_none(self) -> None:
        assert get_prompt_by_name("Nonexistent") is None


class TestGetAllPrompts:
    def test_returns_copy(self) -> None:
        """get_all_prompts() should return a new list, not a reference to PROMPTS."""
        result = get_all_prompts()
        assert result == PROMPTS
        assert result is not PROMPTS
