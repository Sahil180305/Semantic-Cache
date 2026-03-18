# Phase 2: FastAPI REST Server - API Design

**Status:** Design Phase
**Framework:** FastAPI 0.104+
**Python:** 3.10+

---

## Architecture Overview

```
┌─────────────────────────────────────────────┐
│         FastAPI Application Layer            │
├─────────────────────────────────────────────┤
│  - Health & Monitoring                       │
│  - Cache Operations                          │
│  - Search & Similarity                       │
│  - Admin & Management                        │
│  - Multi-Tenant Operations                   │
└──────────────────┬──────────────────────────┘
                   │
         ┌─────────┴─────────┐
         │                   │
    ┌────▼─────┐       ┌────▼──────┐
    │ Phase 1   │       │ Auth/     │
    │ Cache     │       │ Middleware│
    │ System    │       │           │
    └──────────┘       └───────────┘
```

---

## API Endpoints - Complete Specification

### 1. HEALTH & MONITORING

#### GET `/health`
```
Description: System health check
Response: 200 OK

{
  "status": "healthy",
  "cache_level": "l2",
  "redis": "connected",
  "postgres": "connected",
  "uptime_seconds": 3600
}
```

#### GET `/health/detailed`
```
Description: Detailed health status with all services
Response: 200 OK

{
  "status": "healthy",
  "services": {
    "cache_l1": "operational",
    "cache_l2": "operational",
    "redis": "connected",
    "postgres": "healthy"
  },
  "metrics": {
    "cache_hit_rate": 0.85,
    "avg_latency_ms": 5.2,
    "memory_used_mb": 256
  }
}
```

#### GET `/metrics`
```
Description: Prometheus-compatible metrics
Response: 200 OK (text/plain)

# HELP semantic_cache_hits_total Total cache hits
# TYPE semantic_cache_hits_total counter
semantic_cache_hits_total{cache_level="l1"} 5432
semantic_cache_hits_total{cache_level="l2"} 1234
...
```

---

### 2. CACHE OPERATIONS (Core)

#### GET `/api/v1/cache/{key}`
```
Description: Retrieve value from cache
Auth: Required (Bearer token or API key)
Headers: Authorization, X-Tenant-ID (if multi-tenant)

Response: 200 OK
{
  "key": "my_key",
  "value": "cached_value",
  "hit": true,
  "cache_level": "l1",
  "latency_ms": 0.5,
  "ttl_remaining_seconds": 3599
}

Response: 404 Not Found
{
  "key": "my_key",
  "hit": false,
  "message": "Key not found in cache"
}
```

#### PUT `/api/v1/cache/{key}`
```
Description: Cache a value
Auth: Required
Headers: Authorization, X-Tenant-ID

Request Body:
{
  "value": "some_value",
  "ttl_seconds": 3600,  // Optional
  "cost": 100,          // Optional (for cost-aware eviction)
  "metadata": {         // Optional
    "domain": "embedding",
    "priority": "high"
  }
}

Response: 201 Created
{
  "key": "my_key",
  "cached": true,
  "cache_level": "l2",
  "size_bytes": 125
}
```

#### DELETE `/api/v1/cache/{key}`
```
Description: Delete cached value
Auth: Required
Headers: Authorization, X-Tenant-ID

Response: 204 No Content

Response: 404 Not Found
{
  "message": "Key not found"
}
```

#### POST `/api/v1/cache/batch`
```
Description: Get multiple values in one request
Auth: Required

Request Body:
{
  "keys": ["key1", "key2", "key3"]
}

Response: 200 OK
{
  "results": [
    {"key": "key1", "value": "val1", "hit": true},
    {"key": "key2", "value": null, "hit": false},
    {"key": "key3", "value": "val3", "hit": true}
  ],
  "hit_count": 2,
  "miss_count": 1,
  "hit_rate": 0.67
}
```

#### DELETE `/api/v1/cache`
```
Description: Clear all cache (admin only)
Auth: Required + Admin role
Headers: Authorization

Response: 200 OK
{
  "cleared": true,
  "items_cleared": 14523
}
```

---

### 3. SEARCH & SIMILARITY

#### POST `/api/v1/cache/search`
```
Description: Find semantically similar cached queries
Auth: Required
Headers: Authorization, X-Tenant-ID

Request Body:
{
  "query": "what is machine learning",
  "top_k": 5,
  "threshold": 0.8,
  "metric": "cosine"  // cosine, euclidean, manhattan, hamming, jaccard
}

Response: 200 OK
{
  "query": "what is machine learning",
  "metric": "cosine",
  "results": [
    {
      "key": "ml_primer_1",
      "similarity": 0.95,
      "value": "cached_result",
      "cache_level": "l1"
    },
    {
      "key": "ml_basics_2",
      "similarity": 0.88,
      "value": "another_result",
      "cache_level": "l2"
    }
  ],
  "count": 2
}
```

#### POST `/api/v1/similarity/embedding`
```
Description: Generate embedding and find similar
Auth: Required

Request Body:
{
  "text": "machine learning models",
  "provider": "openai",  // openai, huggingface, local
  "top_k": 10,
  "threshold": 0.75
}

Response: 200 OK
{
  "text": "machine learning models",
  "embedding": [0.1, 0.2, ..., 0.9],
  "similar_items": [
    {
      "key": "query_1",
      "distance": 0.05,
      "value": "result_1"
    }
  ],
  "count": 3
}
```

---

### 4. QUERY DEDUPLICATION

#### POST `/api/v1/dedup/register`
```
Description: Register query and check for duplicates
Auth: Required
Headers: X-Tenant-ID

Request Body:
{
  "query": "What is AI?",
  "strategy": "normalized"  // exact, normalized, semantic, prefix
}

Response: 200 OK
{
  "canonical": "what is ai",
  "is_duplicate": false,
  "strategy": "normalized"
}

// If duplicate found:
{
  "canonical": "what is ai",
  "is_duplicate": true,
  "similar_to": "alternate_query_text"
}
```

#### POST `/api/v1/dedup/stats`
```
Description: Get deduplication statistics
Auth: Required
Headers: X-Tenant-ID

Response: 200 OK
{
  "total_deduplicated": 245,
  "unique_queries": 123,
  "reduction_percentage": 49.8,
  "top_duplicates": [
    {
      "canonical": "what is ai",
      "count": 15
    }
  ]
}
```

---

### 5. ADMIN ENDPOINTS

#### GET `/api/v1/admin/stats`
```
Description: Global system statistics
Auth: Required + Admin role

Response: 200 OK
{
  "total_items_cached": 50000,
  "total_memory_mb": 512,
  "l1_capacity_pct": 75,
  "l2_capacity_pct": 45,
  "hit_rate_overall": 0.82,
  "requests_today": 150000,
  "unique_users": 1234
}
```

#### POST `/api/v1/admin/cache/optimize`
```
Description: Trigger cache optimization
Auth: Required + Admin role

Request Body:
{
  "strategy": "aggressive",  // conservative, balanced, aggressive
  "dry_run": false
}

Response: 200 OK
{
  "status": "completed",
  "items_evicted": 234,
  "memory_freed_mb": 45,
  "new_hit_rate": 0.87
}
```

#### POST `/api/v1/admin/cache/compress`
```
Description: Compress cached responses
Auth: Required + Admin role

Request Body:
{
  "min_size_kb": 5,
  "method": "gzip"  // gzip, zlib, deflate
}

Response: 200 OK
{
  "items_compressed": 1234,
  "space_saved_mb": 125.5,
  "compression_ratio": 0.76
}
```

#### GET `/api/v1/admin/policies`
```
Description: Get current caching policies
Auth: Required + Admin role

Response: 200 OK
{
  "l1_policy": {
    "eviction": "LFU",
    "capacity": 10000,
    "ttl_default_seconds": 3600
  },
  "l2_policy": {
    "strategy": "write_through",
    "capacity": 100000
  },
  "advanced": {
    "cost_aware": true,
    "cost_threshold": 50,
    "prefetching_enabled": true
  }
}
```

#### PUT `/api/v1/admin/policies`
```
Description: Update caching policies
Auth: Required + Admin role

Request Body:
{
  "l1_eviction": "LRU",
  "l1_ttl_seconds": 7200,
  "cost_aware_enabled": true
}

Response: 200 OK
{
  "updated": true,
  "policies": {...}
}
```

---

### 6. MULTI-TENANT ENDPOINTS

#### POST `/api/v1/tenant/create`
```
Description: Create new tenant
Auth: Required + Admin role

Request Body:
{
  "tenant_id": "acme_corp",
  "quota_memory_mb": 1000,
  "quota_queries_daily": 100000,
  "quota_request_size_kb": 500
}

Response: 201 Created
{
  "tenant_id": "acme_corp",
  "status": "active",
  "quota": {...}
}
```

#### GET `/api/v1/tenant/{tenant_id}/metrics`
```
Description: Get tenant-specific metrics
Auth: Required
Headers: X-Tenant-ID

Response: 200 OK
{
  "tenant_id": "acme_corp",
  "memory_used_mb": 250,
  "memory_quota_mb": 1000,
  "queries_today": 45000,
  "queries_quota": 100000,
  "hit_rate": 0.88
}
```

#### GET `/api/v1/tenant/{tenant_id}/usage`
```
Description: Detailed tenant usage and limits
Auth: Required + Admin role

Response: 200 OK
{
  "tenant_id": "acme_corp",
  "memory": {
    "used_mb": 250,
    "quota_mb": 1000,
    "percentage": 25
  },
  "queries": {
    "today": 45000,
    "quota": 100000,
    "percentage": 45
  },
  "requests": {
    "avg_size_kb": 5.2,
    "max_size_kb": 500
  }
}
```

#### PUT `/api/v1/tenant/{tenant_id}/quota`
```
Description: Update tenant quota
Auth: Required + Admin role

Request Body:
{
  "memory_mb": 2000,
  "queries_daily": 200000,
  "request_size_kb": 1000
}

Response: 200 OK
{
  "updated": true,
  "new_quota": {...}
}
```

#### DELETE `/api/v1/tenant/{tenant_id}`
```
Description: Delete tenant and clear data
Auth: Required + Admin role
Warning: This is irreversible

Response: 204 No Content
```

#### GET `/api/v1/tenant/verify-isolation`
```
Description: Verify tenant isolation (security check)
Auth: Required + Admin role

Response: 200 OK
{
  "isolated": true,
  "checked_pairs": 145,
  "violations": 0,
  "timestamp": "2026-03-18T10:30:00Z"
}
```

---

## Authentication & Authorization

### Bearer Token

```
GET /api/v1/cache/key
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### API Key

```
GET /api/v1/cache/key
X-API-Key: sk_live_51234567890abcdef
```

### JWT Claims

```json
{
  "sub": "user_123",
  "tenant_id": "acme_corp",
  "role": "user",  // user, admin, superadmin
  "scopes": ["cache:read", "cache:write", "search:read"],
  "exp": 1700000000
}
```

### Roles & Permissions

| Role | Permissions |
|------|-------------|
| `user` | cache:read, cache:write, search:read |
| `admin` | All user perms + admin:read, admin:write, tenant:manage |
| `superadmin` | All permissions |

---

## Response Format

### Success (200, 201, 204)

```json
{
  "success": true,
  "data": {...},
  "timestamp": "2026-03-18T10:30:00Z"
}
```

### Error (400, 401, 403, 404, 500)

```json
{
  "success": false,
  "error": {
    "code": "CACHE_NOT_FOUND",
    "message": "Key not found in cache",
    "details": {...}
  },
  "timestamp": "2026-03-18T10:30:00Z"
}
```

---

## Request/Response Schemas

### Common Headers

```
Authorization: Bearer {token}        // Required for protected endpoints
X-Tenant-ID: tenant_123              // Required for multi-tenant
X-Request-ID: unique-id              // For tracking
Accept: application/json              // Default
Content-Type: application/json        // For POST/PUT
```

### Pagination (if needed)

```
GET /api/v1/items?page=1&limit=50

Response:
{
  "items": [...],
  "pagination": {
    "page": 1,
    "limit": 50,
    "total": 1000,
    "pages": 20
  }
}
```

---

## Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `OK` | 200 | Success |
| `CREATED` | 201 | Resource created |
| `NO_CONTENT` | 204 | Success, no content |
| `BAD_REQUEST` | 400 | Invalid request |
| `UNAUTHORIZED` | 401 | Missing/invalid auth |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `NOT_FOUND` | 404 | Resource not found |
| `CONFLICT` | 409 | Resource conflict |
| `QUOTA_EXCEEDED` | 429 | Tenant quota exceeded |
| `SERVER_ERROR` | 500 | Internal server error |

---

## Rate Limiting

```
X-RateLimit-Limit: 10000
X-RateLimit-Remaining: 9845
X-RateLimit-Reset: 1700000000

// When limit exceeded:
HTTP 429 Too Many Requests
Retry-After: 60
```

---

## Versioning

- Current: `/api/v1/`
- Path-based versioning: `/api/v2/`, `/api/v3/`, etc.
- Deprecated endpoints marked with deprecation headers

---

## Documentation

- **Swagger/OpenAPI:** `GET /docs`
- **ReDoc:** `GET /redoc`
- **OpenAPI JSON:** `GET /openapi.json`

---

## Implementation Roadmap

### Phase 2.1: Foundation & Core Endpoints
- [ ] FastAPI setup
- [ ] Health check endpoints
- [ ] Basic cache operations (GET, PUT, DELETE)
- [ ] Authorization middleware

### Phase 2.2: Advanced Features
- [ ] Search endpoints
- [ ] Batch operations
- [ ] Query deduplication
- [ ] Error handling

### Phase 2.3: Admin & Multi-tenant
- [ ] Admin endpoints
- [ ] Tenant management
- [ ] Policy management
- [ ] Isolation verification

### Phase 2.4: Polish & Production
- [ ] Comprehensive tests
- [ ] Documentation
- [ ] Performance optimization
- [ ] Deployment configs

---

## Testing Strategy

| Test Type | Tools | Coverage |
|-----------|-------|----------|
| Unit | pytest | API functions |
| Integration | pytest + FastAPI TestClient | Full endpoints |
| Load | locust | 10K req/s |
| Security | bandit | Code vulnerabilities |

---

## Deployment

- **Framework:** FastAPI with Uvicorn
- **Server:** gunicorn + uvicorn workers
- **Docker:** Multi-stage Dockerfile
- **Kubernetes:** Helm charts (optional)

---

**Next:** Infrastructure setup and core implementation
