# Semantic Caching Layer for Vector Databases

A production-grade semantic cache that sits between LLM-powered applications and backend AI services, reducing latency and cost through intelligent similarity-aware caching.

## 🚀 Quick Start

```bash
# 1. Start infrastructure
docker-compose up -d

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the API server
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# 4. Test it works
curl http://localhost:8000/health
```

## Overview

This project implements a smart caching layer that goes beyond exact-match caching, using semantic similarity to reuse responses for similar queries.

### Key Features

| Feature | Description |
|---------|-------------|
| **3-Tier Caching** | L1 (Memory <1ms) → L2 (Redis 5-10ms) → L3 (PostgreSQL 10-50ms) |
| **Semantic Matching** | Find similar queries using embeddings & HNSW index |
| **Domain-Adaptive Thresholds** | Auto-adjusts similarity thresholds per domain |
| **Cost-Aware Eviction** | Keeps expensive LLM responses longer |
| **Multi-Tenant Isolation** | Secure tenant separation with quotas |
| **Predictive Warming** | Pre-caches likely queries |

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Your RAG Application                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Semantic Cache API                         │
│  ┌───────────┐  ┌─────────────┐  ┌───────────────────────┐  │
│  │ Embedding │  │   Domain    │  │  Adaptive Thresholds  │  │
│  │  Service  │  │ Classifier  │  │   & Cost Policy       │  │
│  └───────────┘  └─────────────┘  └───────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
  ┌──────────┐         ┌──────────┐         ┌──────────┐
  │ L1 Cache │         │ L2 Cache │         │ L3 Cache │
  │ (Memory) │         │ (Redis)  │         │(Postgres)│
  │   <1ms   │         │  5-10ms  │         │ 10-50ms  │
  │  ~10K    │         │  ~100K   │         │ Millions │
  └──────────┘         └──────────┘         └──────────┘
```

## 📖 Documentation

| Document | Description |
|----------|-------------|
| **[Usage Guide](./docs/guides/USAGE_GUIDE.md)** | Complete usage guide with RAG integration examples |
| **[Architecture](./docs/ARCHITECTURE_COMPARISON.md)** | System architecture and design decisions |
| **[Query Flow](./docs/QUERY_FLOW_EXPLAINED.md)** | How queries flow through the system |
| **[API Reference](./docs/api/)** | Complete API documentation |
| **[Setup Guide](./docs/guides/SETUP.md)** | Detailed installation instructions |

## Usage Examples

### Basic Semantic Caching

```python
import httpx

# Store a query-response pair
response = httpx.post("http://localhost:8000/api/v1/cache/semantic", json={
    "query": "What is machine learning?",
    "response": "Machine learning is a subset of AI...",
    "domain": "technology"
})

# Search for similar queries
response = httpx.post("http://localhost:8000/api/v1/cache/semantic/search", json={
    "query": "Explain ML to me",
    "threshold": 0.85
})

# Returns cached response with 92% similarity match!
print(response.json())
# {"hit": true, "similarity": 0.92, "response": "Machine learning is..."}
```

### RAG Integration

```python
async def rag_with_cache(query: str, retriever, llm):
    # 1. Check cache first
    cache_result = await cache.search(query, threshold=0.85)
    if cache_result.hit:
        return cache_result.response  # Fast path: ~5ms
    
    # 2. Cache miss - run full RAG pipeline
    docs = retriever.get_relevant_documents(query)
    response = llm.generate(query, context=docs)  # Slow path: ~2000ms
    
    # 3. Cache for future queries
    await cache.store(query, response, metadata={"cost": 0.003})
    
    return response
```

See the [Usage Guide](./docs/guides/USAGE_GUIDE.md) for complete examples with LangChain, LlamaIndex, and OpenAI.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with cache status |
| `/api/v1/cache/semantic` | POST | Store with semantic indexing |
| `/api/v1/cache/semantic/search` | POST | Semantic similarity search |
| `/api/v1/cache/{key}` | GET/PUT/DEL | Exact key operations |
| `/api/v1/admin/stats` | GET | Cache statistics |
| `/api/v1/tenant/create` | POST | Create tenant |

## Project Structure

```
semantic-cache/
├── src/
│   ├── api/              # FastAPI endpoints & middleware
│   ├── cache/            # L1 (memory), L2 (Redis), L3 (PostgreSQL)
│   ├── embedding/        # Embedding service (sentence-transformers)
│   ├── similarity/       # HNSW index & similarity search
│   ├── ml/               # Domain classifier, adaptive thresholds
│   ├── multi_tenancy/    # Tenant isolation & quotas
│   └── monitoring/       # Prometheus metrics
├── tests/                # Unit, integration, performance tests
├── docs/                 # Documentation
├── monitoring/           # Grafana dashboards, Prometheus config
└── docker-compose.yml    # Redis, PostgreSQL, monitoring stack
```

## Development Status

| Phase | Status | Features |
|-------|--------|----------|
| **Phase 1**: Core Cache | ✅ Complete | Redis + HNSW, embeddings, monitoring |
| **Phase 2**: Multi-Level | ✅ Complete | L1/L2/L3 tiers, eviction policies |
| **Phase 3**: Intelligence | ✅ Complete | Domain classifier, adaptive thresholds, predictive warming |
| **Phase 4**: Production | ✅ Complete | Multi-tenancy, security, load testing |

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Performance tests
pytest tests/performance/ -v
```

## Monitoring

Access monitoring dashboards:
- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090

Key metrics:
- Cache hit rate by tier
- Latency percentiles (p50, p95, p99)
- Cost savings estimation
- Query throughput

## Contributing

1. Create a feature branch
2. Make changes with tests
3. Run `pytest` and `black`
4. Submit a pull request

## License

MIT License - See LICENSE file for details

## Contact

For questions or contributions, contact the project team.

---

📚 **[Full Usage Guide →](./docs/guides/USAGE_GUIDE.md)**
