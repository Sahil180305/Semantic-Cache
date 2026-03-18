# Phase 2 Technical Decisions Log

## Decision 1: Cache Endpoint Architecture (ACCEPTED)

**Decision**: Implement cache endpoints with Phase 1.5 CacheManager direct integration

**Date Decided**: Session 1, Phase 2
**Status**: ✅ IMPLEMENTED & TESTED

### Context
- Need simple key-value storage with caching semantics
- Phase 1 has fully-tested CacheManager with L1/L2 support
- Must support tenant isolation

### Options Considered
1. **Direct CacheManager integration** (CHOSEN) ✅
   - Pros: Proven, tested, simple, fast
   - Cons: Limited features (just get/set/delete)
   - Best for: Cache abstraction testing

2. Database-backed cache
   - Pros: Persistent, queryable
   - Cons: Slower, more overhead
   - Best for: Production scale

3. Custom cache layer
   - Pros: Custom features
   - Cons: Untested, more code
   - Best for: Special requirements

### Decision
Use direct CacheManager integration. More advanced features (compression, policies) will come in Phase 2.3.

### Result
✅ Phase 2.1 complete: 6/6 tests passing, cache API working

---

## Decision 2: Search Endpoint Integration Approach (PENDING)

**Decision**: Integrate Phase 1.2 (Embedding) + Phase 1.3 (Similarity) for semantic search

**Date Decided**: Session 1, Phase 2.2
**Status**: 🟨 CODE READY, BLOCKED ON DEPENDENCIES

### Context
- Need semantic search capability
- Phase 1 has complete embedding & similarity search services
- Challenge: ML dependencies (sentence-transformers, torch)

### Options Considered
1. **Full ML integration** (CODE READY)
   - Pros: Complete semantic search, real embeddings
   - Cons: Heavy deps, slow startup (~30-60s), complex dependency management
   - Best for: Production with ML infrastructure

2. **Lightweight stubs** (ALTERNATIVE)
   - Pros: Fast startup, no dependencies, works immediately
   - Cons: Placeholder responses, no real semantics
   - Best for: Development/testing without ML
   - Can upgrade later

3. **External ML service** (NOT CHOSEN)
   - Pros: Offload compute, scalable
   - Cons: Network latency, API costs, external dependency
   - Best for: Large scale

### Decision Status
**PENDING**: Next developer chooses based on priorities

**If choosing Full ML Integration**:
```bash
pip install sentence-transformers>=2.2.2
# Then run tests and move forward
```

**If choosing Lightweight Stubs**:
```bash
# Use search_simple.py as placeholder
# Implement real search in Phase 3
```

### Criteria for Decision
- **Time constraints**: If tight → lightweight (30min to deploy)
- **ML expertise**: If has → full integration (test thoroughly)
- **Next priority**: If moving to Phase 2.3 → lightweight
- **User needs**: If semantic search critical → full integration

---

## Decision 3: Authentication Strategy (ACCEPTED)

**Decision**: JWT-based with role-based access control (RBAC) and tenant isolation

**Date Decided**: Phase 2.0
**Status**: ✅ IMPLEMENTED

### Context
- Multi-tenant system needs strong isolation
- Different user roles (admin, user, viewer)
- Need stateless auth for scalability

### Design
```
Token Generation: GET /token
Token Format: JWT with claims (user_id, role, tenant_id)
Validation: FastAPI Depends(get_current_user)
Tenant Isolation: Prefix cache keys with {tenant_id}:
Role Enforcement: Check user.role == "admin" for admin endpoints
```

### Guarantees
- ✅ Tokens signed with JWT_SECRET_KEY
- ✅ No tenant cross-contamination (prefix isolation)
- ✅ Fast validation (no database lookups)
- ✅ Extensible for 3rd-party providers

### Why Not
- ❌ Session-based: Requires server state, not scalable
- ❌ API keys: Less secure than JWT
- ❌ OAuth: Overkill for internal API

---

## Decision 4: Embedding Model Selection (ACCEPTED)

**Decision**: Use sentence-transformers (all-MiniLM-L6-v2) for local embeddings

**Date Decided**: Phase 2.2
**Status**: ✅ DECIDED, PENDING IMPLEMENTATION

### Context
- Need to embed text queries for semantic search
- Want fast, local embeddings (no API calls)
- 384-dimensional embeddings sufficient for semantic cache

### Model Comparison
| Model | Provider | Dims | Speed | Size | Cost |
|-------|----------|------|-------|------|------|
| **all-MiniLM-L6-v2** (CHOSEN) | Local | 384 | Fast | 90MB | Free |
| all-MiniLM-L12-v2 | Local | 384 | Slower | 110MB | Free |
| OpenAI text-embedding-3 | API | 1536 | API latency | N/A | $$$ |
| Cohere-embed | API | 1024 | API latency | N/A | $$$ |

### Rationale
- **384 dims**: Sufficient for cache similarity (research shows diminishing returns beyond)
- **Speed**: ~5-10ms per embedding (acceptable for API)
- **Cost**: Free, local execution
- **Size**: Fits in GPU memory or CPU cache
- **Quality**: Good semantic understanding for cache queries

### Trade-offs Made
- Accuracy vs Speed: MiniLM is good enough
- Local vs Remote: Chose local to avoid API dependency

### Migration Path
If future needs stronger embeddings:
1. Replace model in EmbeddingService initialization
2. Update HNSW dimension parameter
3. No other code changes needed

---

## Decision 5: Similarity Search Index Strategy (ACCEPTED)

**Decision**: HNSW (Hierarchical Navigable Small World) approximate nearest neighbor search

**Date Decided**: Phase 2.2
**Status**: ✅ DECIDED, PENDING TESTING

### Context
- Need to find semantically similar cached queries
- Trade-off: Accuracy vs Speed
- Must handle up to 100K+ cached items

### Comparison
| Algorithm | Speed | Accuracy | Memory | Complexity |
|-----------|-------|----------|--------|-----------|
| **HNSW** (CHOSEN) | O(log N) | 99%+ | Moderate | Complex |
| Faiss IVF | O(log N) | 95% | Low | Medium |
| Exact KNN | O(N) | 100% | High | Simple |
| LSH | O(1) | 80% | Low | Simple |

### Why HNSW
- ✅ Industry standard (used by Weaviate, Pinecone, Qdrant)
- ✅ Excellent recall with small index
- ✅ Efficient memory usage
- ✅ Handles dynamic inserts
- ✅ Configurable accuracy/speed tradeoff

### Parameters Chosen
```
HNSW Configuration (from main.py):
- M = 16              # Connections per node
- ef_construction = 200  # Accuracy during construction
- ef_search = 50      # Trade-off: 50 = 99% recall
- metric = COSINE     # Vector similarity metric
```

### Trade-offs Made
- Construction time vs Query time: More M = faster queries, slower construction
- Memory vs Accuracy: ef decides accuracy/memory tradeoff

---

## Decision 6: Tenant Isolation Strategy (ACCEPTED)

**Decision**: Prefix-based isolation at CacheManager level

**Date Decided**: Phase 2.0
**Status**: ✅ IMPLEMENTED

### Design Pattern
```
All cache operations use format: {tenant_id}:{original_key}
Examples:
  tenant_1:query_abc123
  tenant_2:query_xyz789
  tenant_1:embedding_v1:query_abc
```

### Guarantee
```python
# Even if attacker knows tenant_2's keys:
cache_manager.get("tenant_2:secret")  # Key doesn't exist
# Actual key stored: "tenant_1:secret"
```

### Why Prefix Not Database Table
✅ Prefix:
- Single cache instance
- No schema changes
- Atomic operations
- Simple, proven

❌ Table-per-tenant (rejected):
- Schema management
- Complex migrations
- Multiple database connections
- More moving parts

### Verification Strategy
- ✅ Every endpoint extracts tenant_id from JWT
- ✅ All cache keys prefixed with tenant_id
- ✅ No raw key access without tenant_id
- ✅ Future: test_*.py has isolation test

---

## Decision 7: API Port Management (ACCEPTED)

**Decision**: Primary port 8000, secondary 8001 for testing conflicts

**Date Decided**: Session debugging
**Status**: ✅ RESOLVED

### Resolution
- Production: Use 8000
- Testing: Kill port 8000 before starting tests
- Parallel testing: Could use 8001 if needed

### Why Not Other Ports
- ❌ 3000-9000: Common development ports, often in use
- ❌ 80/443: Require root/admin
- ✅ 8000: Standard for Python/FastAPI

---

## Decision 8: Phase 2.2 Scope - Full vs Lightweight (PENDING)

**Decision**: TBD by next developer

**Date Decided**: March 19, 2026
**Status**: 🟨 PENDING

### Option A: Lightweight (Code Written but Disabled)
- Use search_simple.py (placeholder stubs)
- No ML dependencies
- Fast server startup
- Suitable for: Testing other features, CI/CD pipelines
- Time to deploy: 15 minutes

### Option B: Full Integration (Code Written, Pending Testing)
- Keep search.py with Phase 1.2/1.3
- Install sentence-transformers
- Real semantic search
- Suitable for: Complete feature set, ML testing
- Time to deploy: 1-2 hours

### Recommendation
**Lightweight for Phase 2.3**, then come back to full Phase 2.2 later if time permits.

**Rationale**:
1. Phase 2.1 cache is more important base functionality
2. Phase 2.3 admin is more impactful
3. ML deps are heavy (sentence-transformers ~500MB)
4. Placeholder allows testing infrastructure
5. Can upgrade Phase 2.2 in Phase 3

---

## Decision 9: Service Initialization Order (ACCEPTED)

**Decision**: Initialize services in dependency order during startup

**Date Decided**: Phase 2.0
**Status**: ✅ IMPLEMENTED

### Order (from main.py startup_event)
```
1. CacheManager        (independent)
2. EmbeddingService    (uses CacheManager for embedding cache)
3. SimilarityService   (independent, uses EmbeddingService outputs)
4. AdvancedPolicies    (uses CacheManager)
5. TenantManager       (uses CacheManager)
```

### Why Order Matters
- Services may depend on earlier services
- Failures are logged with clear order
- Easy to add/remove services
- Mirrors feature addition sequence

---

## Decision 10: Documentation Strategy (ACCEPTED)

**Decision**: Three-level documentation for different audiences

**Date Decided**: End of Phase 2.1
**Status**: ✅ DOCUMENTS CREATED

### Documentation Levels

**Level 1: Quick Start** (5 minutes)
- File: `docs/PHASE_2_QUICK_START.md`
- Audience: New developers joining
- Content: Setup, Phase 2.3 overview, common commands

**Level 2: Full Checkpoint** (30 minutes)
- File: `docs/CHECKPOINT_PHASE2.md`
- Audience: Developers continuing/debugging
- Content: All decisions, architecture, code status

**Level 3: Design Documents** (deep reference)
- Files: `docs/PHASE_2_DESIGN.md`, etc.
- Audience: Architects reviewing system
- Content: Why decisions, trade-offs, alternatives

### Maintenance
- Update checkpoint after each major decision
- Update quick start every session
- Review design docs quarterly

---

## Open Questions for Next Developer

1. **Phase 2.2 Direction**: Full ML or lightweight stubs?
   - Affects: Next 1-2 hours
   - Decision: Check project priorities

2. **Performance Tuning**: Is current HNSW config sufficient?
   - Affects: Phase 3 optimization
   - Metrics: Monitor latency, accuracy trade-off

3. **Scale Limits**: How many cached items supported?
   - Current: Design for ~100K
   - Future: Test at scale

4. **Tenant Growth**: How many tenants expected?
   - Prefix isolation works for millions
   - No known limits

---

## Decision Review Schedule

| Document | Next Review | Owner |
|----------|-------------|-------|
| This log | After Phase 2.3 | Development team |
| Checkpoint | Every session | Current developer |
| Quick start | Every major milestone | Document owner |
| Design docs | Before Phase 3 | Architect |

---

**Last Updated**: March 19, 2026, 11:45 PM
**Status**: 10 decisions documented, 2 pending
**Next Review**: Before Phase 2.3 begins
