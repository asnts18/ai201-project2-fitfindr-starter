"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform

    """
    listings = load_listings()

    # Filter by price and size
    filtered = []
    for item in listings:
        if max_price is not None and item["price"] > max_price:
            continue
        if size is not None and size.lower() not in item["size"].lower():
            continue
        filtered.append(item)

    # Score by keyword overlap across title, description, and style_tags
    keywords = [w.lower() for w in description.split()]

    def score(item):
        text = (
            item["title"].lower()
            + " "
            + item["description"].lower()
            + " "
            + " ".join(item["style_tags"]).lower()
        )
        return sum(1 for kw in keywords if kw in text)

    scored = [(score(item), item) for item in filtered]
    scored = [(s, item) for s, item in scored if s > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    """
    client = _get_groq_client()

    item_desc = (
        f"'{new_item['title']}' — {new_item['condition']} condition, "
        f"${new_item['price']:.2f} on {new_item['platform']}. "
        f"Colors: {', '.join(new_item.get('colors', []))}. "
        f"Style tags: {', '.join(new_item.get('style_tags', []))}."
    )

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        prompt = (
            f"A user is considering buying this thrifted item: {item_desc}\n\n"
            "They haven't shared their wardrobe yet. Give them 1-2 general outfit ideas: "
            "what types of bottoms, shoes, and layers would pair well, and what vibe/aesthetic it suits. "
            "Be specific and concise — 2-3 sentences."
        )
    else:
        wardrobe_lines = "\n".join(
            f"- {w['name']} ({w['category']}, colors: {', '.join(w['colors'])}, "
            f"tags: {', '.join(w['style_tags'])})"
            + (f" — {w['notes']}" if w.get("notes") else "")
            for w in wardrobe_items
        )
        prompt = (
            f"A user wants to style this thrifted item: {item_desc}\n\n"
            f"Their current wardrobe:\n{wardrobe_lines}\n\n"
            "Suggest 1-2 specific outfit combinations using named pieces from their wardrobe. "
            "For each outfit, name the exact pieces and include a short styling tip (tuck, roll, layer, etc.). "
            "Be casual, specific, and concise."
        )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        title = new_item.get("title", "this item")
        return (
            f"Couldn't generate outfit suggestions right now — but {title} would pair well "
            "with classic basics like straight-leg jeans and white sneakers."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    """
    if not outfit or not outfit.strip():
        title = new_item.get("title", "this item")
        price = new_item.get("price")
        platform = new_item.get("platform", "a thrift app")
        price_str = f"${price:.2f}" if price is not None else "a great price"
        return (
            f"just copped {title} for {price_str} off {platform} — styling inspo coming soon"
        )

    title = new_item.get("title", "this thrifted piece")
    price = new_item.get("price")
    platform = new_item.get("platform", "a thrift app")
    condition = new_item.get("condition", "")
    price_str = f"${price:.2f}" if price is not None else "a steal"

    prompt = (
        f"Write a 2-3 sentence Instagram/TikTok outfit caption for this look:\n\n"
        f"Thrifted item: {title} — {price_str} on {platform} ({condition} condition)\n"
        f"Outfit: {outfit}\n\n"
        "Rules: write in lowercase, casual first-person voice (like a real OOTD post). "
        "Mention the item name, price, and platform naturally once each. "
        "Capture the vibe in specific terms. No generic phrases like 'slaying' or 'obsessed'."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=1.0,
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return (
            f"just copped {title} for {price_str} off {platform} — styling inspo coming soon"
        )
