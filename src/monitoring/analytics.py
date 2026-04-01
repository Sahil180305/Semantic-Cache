from datetime import datetime
from typing import Dict, Optional, Any
import json
import asyncio

class AnalyticsCollector:
    """Collects and bulk-writes cache performance points to DB."""
    
    def __init__(self, redis_client=None, db_connection=None):
        self.redis = redis_client
        self.db = db_connection
    
    async def log_cache_event(
        self,
        event_type: str,
        tier: str,
        latency_ms: float,
        query_hash: str,
        domain: Optional[str] = None,
        similarity_score: Optional[float] = None,
        tokens_saved: int = 0,
        cost_saved: float = 0.0
    ):
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "tier": tier,
            "latency_ms": latency_ms,
            "query_hash": query_hash,
            "domain": domain,
            "similarity_score": similarity_score,
            "tokens_saved": tokens_saved,
            "cost_saved": cost_saved
        }
        
        if self.redis:
            # Add to redis stream
            try:
                await self.redis.xadd("cache:events", {"data": json.dumps(event)}, maxlen=100000)
            except Exception:
                pass

    async def flush_to_db(self):
        """Standard Postgres implementation instead of timescale."""
        if not self.redis or not self.db:
            return
            
        events = await self.redis.xrange("cache:events", count=1000)
        
        if events:
            # We assume a raw asyncpg interface here.
            await self.db.executemany("""
                INSERT INTO cache_events 
                (timestamp, event_type, tier, latency_ms, query_hash, 
                 domain, similarity_score, tokens_saved, cost_saved)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """, [
                (
                    datetime.fromisoformat(e[1][b"data"].decode("utf-8")["timestamp"]), 
                    json.loads(e[1][b"data"].decode("utf-8"))["event_type"],
                    json.loads(e[1][b"data"].decode("utf-8"))["tier"],
                    json.loads(e[1][b"data"].decode("utf-8"))["latency_ms"],
                    json.loads(e[1][b"data"].decode("utf-8"))["query_hash"],
                    json.loads(e[1][b"data"].decode("utf-8"))["domain"],
                    json.loads(e[1][b"data"].decode("utf-8"))["similarity_score"],
                    json.loads(e[1][b"data"].decode("utf-8"))["tokens_saved"],
                    json.loads(e[1][b"data"].decode("utf-8"))["cost_saved"],
                )
                for e in events
            ])
            await self.redis.xtrim("cache:events", maxlen=0)
