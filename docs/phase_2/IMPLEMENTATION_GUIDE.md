# Phase 2: FastAPI REST Server - Implementation Guide

**Status:** 🚀 Scaffolding Complete  
**Framework:** FastAPI 0.104+  
**Start Time:** Session 8  
**Progress:** Foundation & API Design ✅

---

## Quick Start

### 1. Install Dependencies

```bash
cd semantic-cache

# Install FastAPI and dependencies
pip install fastapi uvicorn python-jose[cryptography] pydantic-settings

# Or use requirements file (once updated)
pip install -r requirements.txt
```

### 2. Run Development Server

```bash
# Set environment
$env:ENVIRONMENT = "development"

# Run with auto-reload
python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# Or directly
python -m src.api.main
```

### 3. Access API

- **API Endpoints:** http://localhost:8000/api/v1/
- **Interactive Docs:** http://localhost:8000/docs (Swagger UI)
- **Alternative Docs:** http://localhost:8000/redoc (ReDoc)
- **OpenAPI JSON:** http://localhost:8000/openapi.json
- **Health Check:** http://localhost:8000/health

### 4. Generate Test Token

```bash
curl -X GET "http://localhost:8000/token?user_id=test_user&tenant_id=test_tenant&role=user"

# Response:
# {
#   "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
#   "token_type": "bearer"
# }
```

Use token in requests:
```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/cache/my_key
```

---

## Project Structure

```
semantic-cache/
├── src/
│   ├── api/                          # Phase 2: FastAPI Application
│   │   ├── __init__.py
│   │   ├── main.py                   # FastAPI app entry point
│   │   ├── config.py                 # Configuration & settings
│   │   ├── schemas.py                # Pydantic request/response models
│   │   ├── routes/                   # API route handlers
│   │   │   ├── __init__.py
│   │   │   ├── health.py             # Health check endpoints
│   │   │   ├── cache.py              # Cache operations (GET/PUT/DELETE)
│   │   │   ├── search.py             # Search & similarity endpoints
│   │   │   ├── admin.py              # Admin management endpoints
│   │   │   └── tenant.py             # Multi-tenant endpoints
│   │   ├── auth/                     # Authentication & Authorization
│   │   │   ├── __init__.py
│   │   │   └── jwt.py                # JWT token handling
│   │   └── middleware/               # Custom middleware
│   │       ├── __init__.py
│   │       ├── error.py              # Error handling
│   │       └── auth.py               # Auth middleware (TBD)
│   │
│   ├── cache/                        # Phase 1: Cache System (imported)
│   ├── embedding/                    # Phase 1: Embeddings (imported)
│   ├── similarity/                   # Phase 1: Similarity Search (imported)
│   └── core/                         # Phase 1: Foundation (imported)
│
├── tests/
│   └── api/                          # Phase 2 API tests
│       ├── test_health.py            # TBD
│       ├── test_cache.py             # TBD
│       ├── test_search.py            # TBD
│       ├── test_admin.py             # TBD
│       └── test_tenant.py            # TBD
│
└── docs/
    ├── phase_2/
    │   ├── API_DESIGN.md             # Complete API specification
    │   ├── IMPLEMENTATION_GUIDE.md   # This file
    │   └── DEPLOYMENT.md             # Deployment configurations
    └── guides/                        # Phase 1 guides (existing)
```

---

## API Endpoints Overview

### ✅ Health & Monitoring
- `GET /health` - Basic health check
- `GET /health/detailed` - Detailed service status
- `GET /metrics` - Prometheus metrics

### ✅ Cache Operations (Stub Implementation)
- `GET /api/v1/cache/{key}` - Get cache value
- `PUT /api/v1/cache/{key}` - Cache value
- `DELETE /api/v1/cache/{key}` - Delete cache entry
- `POST /api/v1/cache/batch` - Batch get operations
- `DELETE /api/v1/cache` - Clear all cache

### ✅ Search & Similarity (Stub Implementation)
- `POST /api/v1/search` - Semantic search
- `POST /api/v1/similarity/embedding` - Generate embedding & search

### ✅ Admin Management (Stub Implementation)
- `GET /api/v1/admin/stats` - System statistics
- `POST /api/v1/admin/cache/optimize` - Optimize cache
- `POST /api/v1/admin/cache/compress` - Compress responses
- `GET /api/v1/admin/policies` - Get policies
- `PUT /api/v1/admin/policies` - Update policies

### ✅ Multi-Tenant Management (Stub Implementation)
- `POST /api/v1/tenant/create` - Create tenant
- `GET /api/v1/tenant/{tenant_id}/metrics` - Get metrics
- `GET /api/v1/tenant/{tenant_id}/usage` - Get usage details
- `PUT /api/v1/tenant/{tenant_id}/quota` - Update quota
- `DELETE /api/v1/tenant/{tenant_id}` - Delete tenant
- `GET /api/v1/tenant/verify-isolation` - Verify isolation

---

## Current Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| **Core Setup** | ✅ | FastAPI app, config, schemas |
| **Routes** | 🟨 Stub | All endpoints created, mock implementations |
| **Health Check** | ✅ | Working with mock data |
| **Authentication** | ✅ | JWT tokens, roles, scopes |
| **Cache Integration** | 🔜 | Ready to integrate Phase 1 |
| **Search Integration** | 🔜 | Ready to integrate Phase 1.3 |
| **Admin Integration** | 🔜 | Ready to integrate Phase 1.7 |
| **Tenant Integration** | 🔜 | Ready to integrate Phase 1.9 |
| **Error Handling** | ✅ | Custom exceptions, error responses |
| **Tests** | ⏳ | TBD - comprehensive test suite |
| **Docs** | ✅ | Full API design documentation |

---

## Configuration

### Environment Variables (.env)

```bash
# API Configuration
ENVIRONMENT=development
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=true
API_WORKERS=4
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql://user:password@localhost/cache_db

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# JWT
JWT_SECRET_KEY=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# Cache Configuration
L1_MAX_CAPACITY=10000
L1_EVICTION_POLICY=LRU
L1_DEFAULT_TTL_SECONDS=3600

L2_MAX_CAPACITY=100000
L2_STRATEGY=write_through

# Features
DEDUPLICATION_ENABLED=true
COST_AWARE_EVICTION_ENABLED=true
MULTI_TENANCY_ENABLED=true
```

---

## Development Workflow

### 1. Implement Endpoint Handler

Each route handler needs to:
1. Accept request parameters
2. Verify authentication (`Depends(get_current_user)`)
3. Verify authorization if needed (`Depends(get_current_admin)`)
4. Get tenant ID if multi-tenant (`Depends(get_tenant_id)`)
5. Call Phase 1 components
6. Return response model

Example:
```python
@router.get("/{key}", response_model=CacheGetResponse)
async def get_cache(
    key: str,
    current_user: TokenPayload = Depends(get_current_user),
    tenant_id: str = Depends(get_tenant_id)
):
    # TODO: Replace mock with Phase 1 manager
    manager = cache_manager  # Get from DI
    result = manager.get(tenant_id, key)
    
    return CacheGetResponse(
        key=key,
        value=result,
        hit=result is not None,
        ...
    )
```

### 2. Write Tests

For each endpoint:
```python
def test_get_cache_hit():
    """Test cache hit scenario."""
    # Setup
    # Call endpoint
    # Assert response
    
def test_get_cache_miss():
    """Test cache miss scenario."""
    # Setup
    # Call endpoint
    # Assert 404
```

### 3. Verify Integration

```bash
# Test single endpoint
curl -H "Authorization: Bearer <token>" \
     http://localhost:8000/api/v1/cache/test_key

# Test with pytest
pytest tests/api/test_cache.py -v
```

---

## Phase 1 Integration Map

### Cache Endpoint Integration
```
GET /api/v1/cache/{key}
    └─> src.cache.manager.CacheManager.get(tenant, key)
        └─> Phase 1.4 (L1), Phase 1.5 (L2)

PUT /api/v1/cache/{key}
    └─> src.cache.manager.CacheManager.put(tenant, key, value, cost)
        └─> Phase 1.4, Phase 1.5, Phase 1.7 (cost-aware)

POST /api/v1/cache/batch
    └─> Phase 1.8 (batch processing)
```

### Search Endpoint Integration
```
POST /api/v1/search
    └─> Phase 1.3 (similarity search)
    └─> Phase 1.6 (deduplication)

POST /api/v1/similarity/embedding
    └─> Phase 1.2 (embedding service)
    └─> Phase 1.3 (similarity search)
```

### Admin Integration
```
POST /api/v1/admin/cache/optimize
    └─> Phase 1.7 (advanced policies)
    └─> Phase 1.8 (performance optimization)

POST /api/v1/admin/cache/compress
    └─> Phase 1.8 (response compressor)
```

### Tenant Integration
```
POST /api/v1/tenant/create
    └─> Phase 1.9 (tenant manager)

GET /api/v1/tenant/{tenant_id}/metrics
    └─> Phase 1.9 (tenant metrics)

GET /api/v1/tenant/verify-isolation
    └─> Phase 1.9 (tenant verifier)
```

---

## Testing Strategy

### Unit Tests
```bash
# Test individual endpoints
pytest tests/api/test_cache.py::test_get_cache -v
pytest tests/api/test_health.py -v
```

### Integration Tests
```bash
# Test with real Phase 1 components
pytest tests/api/ -v
```

### Load Tests
```bash
# Test performance with sustained load
locust -f tests/api/load_test.py
```

---

## Authentication Examples

### Development Token Generation

```bash
# In development, generate token via endpoint
curl -X GET \
  "http://localhost:8000/token?user_id=john&tenant_id=acme&role=user"
```

### API Request with Token

```bash
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

# GET request
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/v1/cache/my_key

# PUT request
curl -X PUT \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"value": "test", "ttl_seconds": 3600}' \
     http://localhost:8000/api/v1/cache/my_key

# Multi-tenant request
curl -H "Authorization: Bearer $TOKEN" \
     -H "X-Tenant-ID: other_tenant" \
     http://localhost:8000/api/v1/cache/my_key
```

### Role-Based Access

```python
# User token - can't access admin endpoints
Token with role="user"

# Admin token - can access admin endpoints
Token with role="admin"
```

---

## Error Handling

All errors follow this format:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "User-friendly message",
    "details": {}
  },
  "timestamp": "2026-03-18T10:30:00Z"
}
```

### Common Error Codes

| Code | HTTP | Meaning |
|------|------|---------|
| `CACHE_NOT_FOUND` | 404 | Key not in cache |
| `UNAUTHORIZED` | 401 | Missing/invalid token |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `QUOTA_EXCEEDED` | 429 | Tenant quota exceeded |
| `SERVER_ERROR` | 500 | Internal server error |

---

## Performance Targets

| Metric | Target | Current |
|--------|--------|---------|
| GET latency | < 10ms | TBD |
| PUT latency | < 50ms | TBD |
| Search latency | < 100ms | TBD |
| Requests/sec | > 1000 | TBD |
| Error rate | < 0.1% | TBD |

---

## Next Steps

### Immediate (Next Session)
1. ✅ Create API design document
2. ✅ Create FastAPI scaffolding
3. ⏳ Implement Phase 1 integration layer
4. ⏳ Write comprehensive tests
5. ⏳ Create load test suite

### Short-term
1. Add request validation
2. Add rate limiting
3. Add monitoring/logging
4. Add caching layer integration
5. Performance optimization

### Medium-term
1. Add GraphQL API
2. Add WebSocket support
3. Add API versioning strategy
4. Add API gateway integration
5. Add service mesh support

---

## Useful Commands

### Run API Server
```bash
# Development
uvicorn src.api.main:app --reload

# Production
gunicorn -w 4 -k uvicorn.workers.UvicornWorker src.api.main:app
```

### Run Tests
```bash
# All tests
pytest tests/api/ -v

# Specific test file
pytest tests/api/test_cache.py -v

# With coverage
pytest tests/api/ --cov=src.api --cov-report=html
```

### API Documentation
```bash
# View Swagger UI
open http://localhost:8000/docs

# View ReDoc
open http://localhost:8000/redoc

# Get OpenAPI JSON
curl http://localhost:8000/openapi.json | jq .
```

---

## Documentation Links

- **[API Design Specification](./API_DESIGN.md)** - Complete endpoint documentation
- **[Phase 1 Guide](../guides/INDEX.md)** - Phase 1 cache system documentation
- **Data Models** - See `src/api/schemas.py`
- **Route Handlers** - See `src/api/routes/`
- **Authentication** - See `src/api/auth/jwt.py`

---

## Contributors

**Phase 2 Implementation:** Session 8 (Ongoing)

---

## Checklist for Phase 2 Completion

- [x] API design documentation
- [x] FastAPI project scaffolding
- [x] Configuration management
- [x] Request/response schemas
- [x] Health check endpoints
- [x] Cache operation stubs
- [x] Search endpoint stubs
- [x] Admin endpoint stubs
- [x] Tenant endpoint stubs
- [x] Authentication & authorization
- [x] Error handling
- [ ] Phase 1 integration
- [ ] Comprehensive tests
- [ ] Load testing
- [ ] Performance optimization
- [ ] Docker containerization
- [ ] Kubernetes manifests
- [ ] Production deployment

**Phase 2 ETA:** 2-3 sessions for full implementation and testing

---

**Status: 🚀 Ready for Phase 1 Integration**
