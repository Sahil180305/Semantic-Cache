# Feature Reference

This document describes all features implemented in the Semantic Cache system, organized by phase.

---

## Phase 5: Semantic Enhancements

### Query Normalization
**File:** `src/ml/query_parser.py` — `QueryNormalizer`

Canonicalizes queries before embedding to increase cache hit rates.

| Input | Normalized Output |
|-------|------------------|
| "What is Python?" | "explain python" |
| "Tell me about machine learning" | "explain machine learning" |
| "How do I sort a list?" | "how to sort a list" |

**Integration:** Automatically applied in `CacheManager.get_semantic_async()` and `put_semantic_async()`.

---

### Multi-Intent Detection
**File:** `src/ml/query_parser.py` — `RuleBasedIntentDetector`

Splits complex queries (joined by `and`, `also`, `as well as`, `;`) into atomic sub-queries that are independently cached.

**Endpoint:** `POST /api/v1/cache/semantic/multi/search`

```json
// Request
{ "query": "What is Python and how does list comprehension work?" }

// Response
{
  "sub_queries": [
    { "id": "sq_1", "text": "What is Python", "hit": true, "response": "..." },
    { "id": "sq_2", "text": "how does list comprehension work", "hit": false, "response": null }
  ],
  "all_hit": false,
  "hit_ratio": 0.5,
  "synthesized_response": null
}
```

**LLM Synthesis Wrapper:** `LLMIntentDetector` in `query_parser.py` provides a stub for future integration with OpenAI/Gemini to synthesize multi-part answers.

---

## Phase 6: Production Resilience

### Stale-While-Revalidate (SWR)
**File:** `src/cache/cache_manager.py` — `get_or_compute()`
**Base:** `src/cache/base.py` — `CacheEntry.is_stale()`

Serve stale (expired) cache entries instantly to the user while asynchronously refreshing in background.

```
TTL Zone:     [0 ──────────── TTL ──────── TTL×stale_multiplier ──────── ∞]
Behavior:     [    FRESH HIT     |   STALE HIT (+ background refresh)  | MISS ]
```

**Parameters:**
- `ttl_seconds` — normal TTL before entry is "stale"
- `stale_multiplier` (default: `2.0`) — grace factor; entries within `TTL × multiplier` are served stale

**Anti-thundering-herd:** `CacheEntry.is_refreshing` flag prevents duplicate background tasks.

---

### Streaming Response Cache
**Files:** `src/cache/streaming.py`, `src/api/routes/cache.py`

Intercepts LLM token streams, records per-token `delay_ms` offsets, then replays them on cache hits with authentic timing.

**Endpoint:** `POST /api/v1/cache/semantic/stream`

```
First call:   SSE stream (MISS)  → tokens cached with timing
Second call:  SSE stream (HIT)   → tokens replayed at original speed
Headers:      X-Cache-Status: HIT | MISS
```

**`StreamingCache` API:**
```python
# Intercept & cache
async for token in stream_cache.stream_and_cache(key, token_generator, metadata):
    ...

# Replay cached stream
stream = await stream_cache.get_stream(key, speed_multiplier=1.0)
```

---

### Analytics Backend
**Files:** `src/monitoring/analytics.py`, `src/api/routes/analytics.py`

Collects performance events via Redis Streams and aggregates them using standard PostgreSQL (no TimescaleDB required).

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/metrics/realtime` | Live hit rates from in-memory `CacheManager.metrics` |
| `GET /api/v1/metrics/historical` | Time-bucketed stats (`DATE_TRUNC`) from Postgres |
| `GET /api/v1/insights/top-queries` | Top queries by hit frequency |
| `WS /ws/realtime` | Pushes JSON hit rates every 5 seconds |

**DB Schema (standard PostgreSQL):**
```sql
CREATE TABLE cache_events (
    timestamp         TIMESTAMPTZ,
    event_type        VARCHAR,     -- 'hit' | 'miss'
    tier              VARCHAR,     -- 'l1' | 'l2' | 'l3'
    latency_ms        FLOAT,
    query_hash        VARCHAR,
    domain            VARCHAR,
    similarity_score  FLOAT,
    tokens_saved      INT,
    cost_saved        FLOAT
);
```

---

### Circuit Breaker
**File:** `src/core/circuit_breaker.py`

Prevents cascading failures when the embedding service or LLM compute function is unavailable.

**State Machine:**
```
CLOSED ──(failure_threshold reached)──► OPEN
OPEN   ──(recovery_timeout elapsed)───► HALF_OPEN
HALF_OPEN ──(3 successes)────────────► CLOSED
HALF_OPEN ──(any failure)────────────► OPEN
```

**Default Config:**
| Parameter | Value |
|-----------|-------|
| `failure_threshold` | 5 |
| `recovery_timeout` | 30s (embedding) / 60s (compute) |
| `half_open_max_calls` | 3 |

**Integration:** Wraps `_embedding_service.embed_text()` in `get_semantic_async()` and `put_semantic_async()`, and wraps `compute_fn()` in `get_or_compute()`.

---

## Phase 7: Context-Aware Smart Routing

### Smart Cache Router
**File:** `src/cache/context.py`

Auto-detects whether a query is stateless or conversational, routing to the appropriate cache without any changes to the existing `CacheManager`.

```
Query → ContextAnalyzer → QueryType
                           ├── STATELESS  → SemanticCache (existing, unchanged)
                           ├── CONTEXTUAL → ContextAwareCache (new)
                           └── AMBIGUOUS  → try context first, fallback to semantic
```

**Detection Logic:**

| Signal | Classification | Confidence |
|--------|---------------|------------|
| Matches STATELESS_PATTERNS (e.g. "What is…") | STATELESS | 0.95 |
| Matches CONTEXTUAL_PATTERNS (e.g. "What about it…") | CONTEXTUAL | 0.90 |
| Contains reference pronouns (it/this/that/they) + has history | CONTEXTUAL | 0.75 |
| Contains reference pronouns, no history | AMBIGUOUS | 0.50 |
| Short query (≤ 3 words) + has history | CONTEXTUAL | 0.70 |
| Default | STATELESS | 0.80 |

---

### Context-Aware Cache
**File:** `src/cache/context.py` — `ContextAwareCache`

Caches responses using a **composite key** derived from both the query text and the recent conversation history.

```python
ContextualCacheKey.combined_hash = sha256(
    sha256(last_3_turns_json)[:16] + ":" + sha256(query)[:16]
)
```

**Storage strategy:**
- Exact match: checked in L1 → L2 using `ctx:{combined_hash}` key
- Semantic match: searches index using embedding of `[context_text | Query: query]`
- Threshold: `0.88` (stricter than stateless `0.85` to account for context sensitivity)
- TTL: shorter (1 hour) vs stateless (24 hours)

---

### Chat Endpoint
**Endpoint:** `POST /api/v1/cache/chat`

The unified entry point for all conversational usage.

```http
POST /api/v1/cache/chat
Content-Type: application/json
X-Conversation-Id: conv-abc123
X-Conversation-History: [{"role":"user","content":"What is Python?"},{"role":"assistant","content":"Python is..."}]

{
  "query": "How does it compare to Ruby?"
}
```

**Response:**
```json
{
  "response": "...",
  "cached": true,
  "cache_type": "contextual",
  "routed_to": "context_cache"
}
```

No `X-Conversation-History` header → treated as stateless, routed to existing semantic cache automatically.

---

## Future Improvements

See [`future_improvements.md`](../brain/*/future_improvements.md) for planned upgrades:

1. **NER with spaCy** — Replace regex entity extraction in `ContextAnalyzer._extract_entities()` with `spacy.load("en_core_web_sm")` for production-grade entity recognition.
2. **LLM Summarization** — Stub `ContextAwareCache._generate_summary()` is ready; wire in an OpenAI/Gemini client to compress long conversation histories before embedding.
