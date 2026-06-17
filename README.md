# FitFindr

A multi-tool AI agent that helps users find secondhand clothing pieces and figure out how to wear them. FitFindr searches a mock thrift-store dataset, generates outfit suggestions against the user's wardrobe, and produces a shareable social-media caption — all from a single natural-language query.

---

## Running the App

```bash
pip install -r requirements.txt
# add your key to .env: GROQ_API_KEY=your_key_here
python app.py        # Gradio UI at http://localhost:7860
python agent.py      # CLI smoke test (happy path + error path)
pytest tests/        # run all unit tests
```

---

## Project Structure

```
fitfindr/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example wardrobe
├── utils/
│   └── data_loader.py         # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
├── tools.py                   # Three tool implementations
├── agent.py                   # Planning loop + session state
├── app.py                     # Gradio UI
├── tests/
│   └── test_tools.py          # 16 pytest tests (all passing)
├── planning.md                # Spec and agent diagram
└── requirements.txt
```

---

## Tool Inventory

### `search_listings(description, size, max_price)`

| Parameter | Type | Meaning |
|---|---|---|
| `description` | `str` | Natural-language keywords describing the item (e.g. `"vintage graphic tee"`) |
| `size` | `str \| None` | Size string to filter by; case-insensitive substring match against the listing's `size` field. `None` skips size filtering. |
| `max_price` | `float \| None` | Maximum price (inclusive). `None` skips price filtering. |

**Returns:** A list of listing dicts sorted by relevance score (highest first). Each dict contains: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand`, `platform`. Returns `[]` on no match — never raises.

**Purpose:** Translates the user's search intent into filtered, ranked results from the mock dataset without any LLM call.

---

### `suggest_outfit(new_item, wardrobe)`

| Parameter | Type | Meaning |
|---|---|---|
| `new_item` | `dict` | A single listing dict as returned by `search_listings` |
| `wardrobe` | `dict` | Wardrobe object with an `"items"` key containing a list of wardrobe item dicts (may be empty) |

**Returns:** A non-empty string with 1–2 outfit combinations. If the wardrobe is empty, returns general styling advice based on the item's style tags. Never returns an empty string.

**Purpose:** Uses the Groq LLM (`llama-3.3-70b-versatile`) to suggest specific pairings between the new find and the user's existing wardrobe.

---

### `create_fit_card(outfit, new_item)`

| Parameter | Type | Meaning |
|---|---|---|
| `outfit` | `str` | The outfit suggestion string returned by `suggest_outfit` |
| `new_item` | `dict` | The selected listing dict (provides `title`, `price`, `platform`, `condition`) |

**Returns:** A 2–3 sentence lowercase Instagram-style caption referencing the item name, price, platform, and outfit vibe. Uses `temperature=1.0` to vary output across calls.

**Purpose:** Produces a shareable caption suitable for an OOTD post, grounding the agent's output in a social-media-native format.

---

## Planning Loop

The agent runs a **linear conditional loop** in `agent.py`:

1. **Parse** the query with regex: extract `max_price` from `$N` patterns first, strip those tokens, then extract `size` from `size XYZ` or standalone letter-sizes (S, M, L, XL, etc.), and use the remaining text as `description`.
2. **Search** — call `search_listings(description, size, max_price)`.
   - If results are **empty** → set `session["error"]` to a user-facing message and **return early**. `suggest_outfit` and `create_fit_card` are never called.
   - If results are **non-empty** → set `session["selected_item"] = results[0]` and continue.
3. **Suggest** — call `suggest_outfit(selected_item, wardrobe)`. Always proceeds; empty wardrobe is handled inside the tool.
4. **Caption** — call `create_fit_card(outfit_suggestion, selected_item)`. Always proceeds; missing outfit is handled inside the tool.
5. **Return** the completed session dict.

The loop has exactly one early-exit point: the empty-search check. Everything downstream runs unconditionally if a result was found.

---

## State Management

A `session` dict is initialized at the start of each `run_agent()` call and passed through the loop:

```python
session = {
    "query":             # original user input (str)
    "parsed":            # {"description": str, "size": str|None, "max_price": float|None}
    "search_results":    # full list returned by search_listings
    "selected_item":     # results[0] — passed to suggest_outfit and create_fit_card
    "wardrobe":          # wardrobe dict passed in by the caller
    "outfit_suggestion": # string returned by suggest_outfit
    "fit_card":          # string returned by create_fit_card
    "error":             # None on success, or a user-facing error string on early exit
}
```

No tool reads from `session` directly — the planning loop reads each key and passes values explicitly as arguments, keeping tools independently testable.

---

## Error Handling

| Tool | Failure mode | Agent response |
|---|---|---|
| `search_listings` | No listings match description/size/price | Sets `session["error"]` and returns immediately. User sees: *"No listings found for 'designer ballgown' in size XXS under $5. Try a higher price, a different size (e.g. 'S/M' instead of 'S'), or simpler keywords."* The other two tools are never called. |
| `suggest_outfit` | Wardrobe is empty (`wardrobe["items"] == []`) | Calls the LLM with a general styling prompt (no wardrobe context). Returns advice like *"Pair with straight-leg jeans and white sneakers for a clean streetwear look."* — no crash, no empty string. |
| `suggest_outfit` | LLM API error (network, rate limit, etc.) | Catches exception; returns: *"Couldn't generate outfit suggestions right now — but [item title] would pair well with classic basics like straight-leg jeans and white sneakers."* |
| `create_fit_card` | `outfit` is empty or whitespace-only | Skips LLM call; returns template: *"just copped [title] for $[price] off [platform] — styling inspo coming soon"* |
| `create_fit_card` | LLM API error | Catches exception; returns the same fallback template. |

**Concrete test example:** `search_listings("designer ballgown", size="XXS", max_price=5)` returns `[]`. The agent returns the error message and does not call `suggest_outfit` with a `None` item. Covered by `test_search_empty_results` in `tests/test_tools.py`.

---

## AI Tool Usage

### Instance 1 — `search_listings` implementation

**Input to Claude:** The Tool 1 spec block from `planning.md` (inputs with types, all return-value field names, failure mode), plus the field names from `data/listings.json`.

**What it produced:** A working function that loaded listings, filtered by price and size, and scored by keyword overlap using `in` membership on a concatenated string.

**What I changed:** The initial version forgot to `.lower()` the `style_tags` list before joining, making tag matching case-sensitive. I also removed a generated docstring that repeated the spec verbatim — the spec is already in `planning.md`.

### Instance 2 — Planning loop (`run_agent`) implementation

**Input to Claude:** The Planning Loop section, State Management section, and the Mermaid architecture diagram from `planning.md`, all together in one prompt.

**What it produced:** A working loop that matched the spec's conditional structure — search, early-exit on empty, then suggest and caption in sequence.

**What I changed:** The regex for size extraction matched bare numbers (e.g. `30` from `$30`) as sizes, so `"vintage graphic tee under $30"` found size-W30 khakis instead of tees. Fix: added a price-stripping step before size extraction runs, and narrowed the size regex to named letter-sizes only (S/M/M/L/XL etc.) rather than any bare digit sequence.

---

## Spec Reflection

The `planning.md` spec held up well for the happy path. Two things needed adjustment during implementation:

**Query parsing order:** The spec said "extract size and price" but didn't specify ordering. Extracting size before stripping price caused bare numbers to bleed into the size match. The fix was a one-line reorder, but a tighter spec would note: *"remove price tokens before attempting size extraction."*

**Size substring matching:** The spec described "case-insensitive substring match" for size. This works (M matches S/M) but also matches M anywhere in a size string. For the mock dataset this is fine; a production system would need exact-token matching to avoid false positives on size strings like "XL (oversized M fit)".
