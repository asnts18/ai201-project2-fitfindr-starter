"""
Tests for FitFindr tools.
Run with: pytest tests/
"""

import pytest
from unittest.mock import patch, MagicMock

from tools import search_listings, suggest_outfit, create_fit_card


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_item():
    return {
        "id": "lst_002",
        "title": "Y2K Baby Tee — Butterfly Print",
        "description": "Super cute early 2000s baby tee with butterfly graphic.",
        "category": "tops",
        "style_tags": ["y2k", "vintage", "graphic tee"],
        "size": "S/M",
        "condition": "excellent",
        "price": 18.0,
        "colors": ["white", "pink", "purple"],
        "brand": None,
        "platform": "depop",
    }


@pytest.fixture
def example_wardrobe():
    from utils.data_loader import get_example_wardrobe
    return get_example_wardrobe()


@pytest.fixture
def empty_wardrobe():
    return {"items": []}


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter():
    results = search_listings("jeans", size="M", max_price=100)
    # all returned items must have "m" somewhere in their size string
    for item in results:
        assert "m" in item["size"].lower()


def test_search_returns_list_of_dicts():
    results = search_listings("vintage", size=None, max_price=200)
    assert isinstance(results, list)
    if results:
        assert isinstance(results[0], dict)
        assert "title" in results[0]
        assert "price" in results[0]


def test_search_no_exception_on_empty_description():
    results = search_listings("", size=None, max_price=100)
    assert isinstance(results, list)


def test_search_results_sorted_by_relevance():
    # Items matching more keywords should come first
    results = search_listings("vintage denim jacket", size=None, max_price=200)
    if len(results) >= 2:
        # First result should mention at least one keyword in title/description/tags
        first = (
            results[0]["title"] + " " +
            results[0]["description"] + " " +
            " ".join(results[0]["style_tags"])
        ).lower()
        assert any(kw in first for kw in ["vintage", "denim", "jacket"])


# ── suggest_outfit ────────────────────────────────────────────────────────────

def _mock_groq_response(text):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = text
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


def test_suggest_outfit_returns_string(sample_item, example_wardrobe):
    with patch("tools._get_groq_client", return_value=_mock_groq_response(
        "Pair with baggy jeans and chunky sneakers for a 90s vibe."
    )):
        result = suggest_outfit(sample_item, example_wardrobe)
    assert isinstance(result, str)
    assert len(result) > 0


def test_suggest_outfit_empty_wardrobe_no_crash(sample_item, empty_wardrobe):
    with patch("tools._get_groq_client", return_value=_mock_groq_response(
        "This tee pairs well with straight-leg jeans and white sneakers."
    )):
        result = suggest_outfit(sample_item, empty_wardrobe)
    assert isinstance(result, str)
    assert len(result) > 0


def test_suggest_outfit_empty_wardrobe_calls_llm(sample_item, empty_wardrobe):
    mock_client = _mock_groq_response("General styling advice here.")
    with patch("tools._get_groq_client", return_value=mock_client):
        suggest_outfit(sample_item, empty_wardrobe)
    # LLM should still be called even with empty wardrobe
    assert mock_client.chat.completions.create.called


def test_suggest_outfit_llm_error_returns_fallback(sample_item, example_wardrobe):
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("API error")
    with patch("tools._get_groq_client", return_value=mock_client):
        result = suggest_outfit(sample_item, example_wardrobe)
    assert isinstance(result, str)
    assert len(result) > 0
    # Should mention the item title in fallback
    assert sample_item["title"] in result or "basics" in result.lower()


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_create_fit_card_returns_string(sample_item):
    outfit = "Baggy jeans + chunky white sneakers + this tee tucked at the front."
    with patch("tools._get_groq_client", return_value=_mock_groq_response(
        "thrifted this y2k butterfly tee off depop for $18 and it's giving everything 🦋"
    )):
        result = create_fit_card(outfit, sample_item)
    assert isinstance(result, str)
    assert len(result) > 0


def test_create_fit_card_empty_outfit_returns_fallback(sample_item):
    result = create_fit_card("", sample_item)
    assert isinstance(result, str)
    assert len(result) > 0
    # Should not crash or return empty
    assert "Y2K Baby Tee" in result or "depop" in result or "18" in result


def test_create_fit_card_whitespace_outfit_returns_fallback(sample_item):
    result = create_fit_card("   ", sample_item)
    assert isinstance(result, str)
    assert len(result) > 0


def test_create_fit_card_llm_error_returns_fallback(sample_item):
    outfit = "Baggy jeans and sneakers."
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("API error")
    with patch("tools._get_groq_client", return_value=mock_client):
        result = create_fit_card(outfit, sample_item)
    assert isinstance(result, str)
    assert len(result) > 0


def test_create_fit_card_missing_price(sample_item):
    item_no_price = {k: v for k, v in sample_item.items() if k != "price"}
    result = create_fit_card("", item_no_price)
    assert isinstance(result, str)
    assert len(result) > 0
