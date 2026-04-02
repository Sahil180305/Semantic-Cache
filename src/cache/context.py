from enum import Enum
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import re
import hashlib
import json
from datetime import datetime

class QueryType(Enum):
    STATELESS = "stateless"       # "What is Python?"
    CONTEXTUAL = "contextual"     # "What about its performance?" (refers to Python)
    AMBIGUOUS = "ambiguous"       # Could be either - needs clarification

@dataclass
class AnalyzedQuery:
    query_type: QueryType
    original_query: str
    normalized_query: str
    context_dependencies: List[str]  
    confidence: float
    suggested_action: str

class ContextAnalyzer:
    """
    Detects if query needs conversation context or can stand alone.
    """
    
    CONTEXTUAL_PATTERNS = [
        r"^(what|how) about (that|this|it|those|them)",
        r"^(and|but|so|then|also)",
        r"^(what|which|who) (is|are|was|were) (that|this|it|they)",
        r"^(can you|could you) (elaborate|explain more|clarify)",
        r"^(why|when|where) (is|are|was|were|did|do|does)",
        r"^(tell me|give me) more",
        r"^(yes|no|maybe|sure|ok|okay)",
        r"^(it|that|this) (sounds|seems|looks|appears)",
        r"^(what|how) (do you|does that) mean",
        r"^(i|we) (see|understand|think|believe|agree|disagree)",
    ]
    
    STATELESS_PATTERNS = [
        r"^(what is|who is|where is|when is|how to|why is)",
        r"^(explain|describe|define|compare|contrast|list)",
        r"^(generate|create|write|code|build|make)",
        r"^(calculate|compute|solve|find|search)",
    ]
    
    REFERENCE_WORDS = {
        "it", "this", "that", "they", "them", "their", "there",
        "he", "she", "his", "her", "him", "these", "those",
        "the former", "the latter", "the above", "the previous"
    }
    
    def __init__(self, embedding_service=None):
        self.embedder = embedding_service
    
    async def analyze(
        self, 
        query: str,
        conversation_history: Optional[List[Dict]] = None
    ) -> AnalyzedQuery:
        query_lower = query.lower().strip()
        normalized = self._normalize(query)
        
        for pattern in self.STATELESS_PATTERNS:
            if re.match(pattern, query_lower):
                return AnalyzedQuery(
                    query_type=QueryType.STATELESS,
                    original_query=query,
                    normalized_query=normalized,
                    context_dependencies=[],
                    confidence=0.95,
                    suggested_action="use_semantic_cache"
                )
        
        for pattern in self.CONTEXTUAL_PATTERNS:
            if re.match(pattern, query_lower):
                deps = self._extract_dependencies(query, conversation_history) if conversation_history else []
                return AnalyzedQuery(
                    query_type=QueryType.CONTEXTUAL,
                    original_query=query,
                    normalized_query=normalized,
                    context_dependencies=deps,
                    confidence=0.90,
                    suggested_action="use_context_cache"
                )
        
        words = set(query_lower.split())
        has_references = bool(words & self.REFERENCE_WORDS)
        
        if has_references:
            if conversation_history:
                deps = self._extract_dependencies(query, conversation_history)
                return AnalyzedQuery(
                    query_type=QueryType.CONTEXTUAL,
                    original_query=query,
                    normalized_query=normalized,
                    context_dependencies=deps,
                    confidence=0.75,
                    suggested_action="use_context_cache"
                )
            else:
                return AnalyzedQuery(
                    query_type=QueryType.AMBIGUOUS,
                    original_query=query,
                    normalized_query=normalized,
                    context_dependencies=[],
                    confidence=0.50,
                    suggested_action="treat_as_stateless_or_ask_clarification"
                )
        
        if len(query.split()) <= 3 and conversation_history:
            return AnalyzedQuery(
                query_type=QueryType.CONTEXTUAL,
                original_query=query,
                normalized_query=normalized,
                context_dependencies=self._extract_dependencies(query, conversation_history),
                confidence=0.70,
                suggested_action="use_context_cache"
            )
        
        return AnalyzedQuery(
            query_type=QueryType.STATELESS,
            original_query=query,
            normalized_query=normalized,
            context_dependencies=[],
            confidence=0.80,
            suggested_action="use_semantic_cache"
        )
    
    def _extract_dependencies(
        self, 
        query: str,
        conversation_history: List[Dict]
    ) -> List[str]:
        dependencies = []
        query_lower = query.lower()
        recent_turns = conversation_history[-3:]  
        for turn in recent_turns:
            if turn.get("role") == "assistant":
                entities = self._extract_entities(turn.get("content", ""))
                for entity in entities:
                    if any(ref in query_lower for ref in [entity.lower(), "it", "this", "that"]):
                        dependencies.append(entity)
        return list(set(dependencies)) 
    
    def _extract_entities(self, text: str) -> List[str]:
        capitalized = re.findall(r'\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\b', text)
        quoted = re.findall(r'"([^"]+)"', text)
        return capitalized + quoted
    
    def _normalize(self, query: str) -> str:
        normalized = query.lower().strip()
        normalized = re.sub(r'\s+', ' ', normalized)
        normalized = re.sub(r'[^\w\s?]', '', normalized)
        return normalized

@dataclass
class ConversationContext:
    conversation_id: str
    turns: List[Dict] 
    summary: Optional[str]  
    key_entities: List[str] 
    
    def to_embedding_text(self) -> str:
        recent = self.turns[-4:] if len(self.turns) > 4 else self.turns
        context_text = " | ".join([
            f"{t['role']}: {t['content'][:100]}" 
            for t in recent
        ])
        if self.summary:
            context_text = f"Summary: {self.summary} | {context_text}"
        return context_text

@dataclass
class ContextualCacheKey:
    context_hash: str     
    query_hash: str        
    combined_hash: str     
    
    @classmethod
    def create(cls, query: str, context: ConversationContext) -> "ContextualCacheKey":
        context_str = json.dumps(context.turns[-3:], sort_keys=True)
        ctx_hash = hashlib.sha256(context_str.encode()).hexdigest()[:16]
        q_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        combined = hashlib.sha256(f"{ctx_hash}:{q_hash}".encode()).hexdigest()[:24]
        
        return cls(context_hash=ctx_hash, query_hash=q_hash, combined_hash=combined)

class ContextAwareCache:
    """
    Caches responses based on query + conversation context
    """
    def __init__(self, base_cache_manager, embedding_service):
        self.cache = base_cache_manager 
        self.embedder = embedding_service
        self.analyzer = ContextAnalyzer(embedding_service)
        self.max_context_turns = 5
        self.similarity_threshold = 0.88  
    
    async def get(
        self,
        query: str,
        conversation_id: str,
        conversation_history: List[Dict]
    ) -> Dict:
        context = ConversationContext(
            conversation_id=conversation_id,
            turns=conversation_history,
            summary=await self._generate_summary(conversation_history),
            key_entities=self._extract_entities_from_history(conversation_history)
        )
        
        cache_key = ContextualCacheKey.create(query, context)
        
        cached = await self._get_exact(cache_key.combined_hash)
        if cached:
            return {
                "hit": True,
                "response": cached["response"],
                "source": "context_cache_exact",
                "context_match": "exact"
            }
        
        semantic_match = await self._get_semantic(query, context)
        if semantic_match:
            return {
                "hit": True,
                "response": semantic_match["response"],
                "source": "context_cache_semantic",
                "context_match": "similar",
                "similarity": semantic_match["similarity"]
            }
        
        return {
            "hit": False,
            "cache_key": cache_key.combined_hash,
            "context": context
        }
    
    async def set(
        self,
        query: str,
        response: str,
        conversation_id: str,
        conversation_history: List[Dict]
    ):
        context = ConversationContext(
            conversation_id=conversation_id,
            turns=conversation_history,
            summary=None,
            key_entities=[]
        )
        
        cache_key = ContextualCacheKey.create(query, context)
        embedding_text = f"{context.to_embedding_text()} | Query: {query}"
        
        embedding_record = await self.embedder.embed_text(embedding_text)
        
        # Store using the manager which triggers Tier 1 -> Tier N. 
        # But we create a special entry manually to route it to context-namespace
        from src.cache.base import CacheEntry
        entry = CacheEntry(
             query_id=f"ctx:{cache_key.combined_hash}",
             query_text=embedding_text,
             embedding=embedding_record.embedding,
             response=response,
             metadata={"cv_id": conversation_id, "ctx_hash": cache_key.context_hash},
        )
        entry.calculate_memory(len(embedding_record.embedding))
        self.cache.put(entry)
        
    async def _get_exact(self, combined_hash: str) -> Optional[Dict]:
        hit = self.cache.l1_cache.get(f"ctx:{combined_hash}")
        if hit:
            return {"response": hit.response}
        if self.cache.l2_cache:
            hit = await self.cache.l2_cache.get(f"ctx:{combined_hash}")
            if hit:
                self.cache.l1_cache.put(hit)
                return {"response": hit.response}
        return None
    
    async def _get_semantic(self, query: str, context: ConversationContext) -> Optional[Dict]:
        # Perform semantic index search locally if available
        if not self.cache._index_manager:
            return None
        embedding_text = f"{context.to_embedding_text()} | Query: {query}"
        embedding_record = await self.embedder.embed_text(embedding_text)
        
        results = self.cache._index_manager.search(
            query_embedding=embedding_record.embedding,
            limit=3
        )
        if results:
            best = results[0]
            # Since _index_manager returns dicts holding item_id and metrics:
            if best["similarity"] > self.similarity_threshold:
                 # Fetch exact from cache
                 hit = self.cache.l1_cache.get(best["item_id"]) or (await self.cache.l2_cache.get(best["item_id"]) if self.cache.l2_cache else None)
                 if hit:
                     return {
                         "response": hit.response,
                         "similarity": best["similarity"]
                     }
        return None
    
    async def _generate_summary(self, history: List[Dict]) -> Optional[str]:
        # Fast algorithm stub for NER without LLM
        return None
    
    def _extract_entities_from_history(self, history: List[Dict]) -> List[str]:
        all_text = " ".join([turn.get("content", "") for turn in history])
        return self.analyzer._extract_entities(all_text)

class SmartCacheRouter:
    """
    Routes queries to appropriate cache based on type
    NO changes to existing SemanticCache needed!
    """
    def __init__(self, cache_manager, embedding_service):
        self.cache_manager = cache_manager
        self.context_cache = ContextAwareCache(cache_manager, embedding_service)
        self.analyzer = ContextAnalyzer(embedding_service)
        
        self.metrics = {
            "stateless_hits": 0,
            "contextual_hits": 0,
            "routing_decisions": []
        }
    
    async def get(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None,
        **kwargs
    ) -> Dict:
        """Unified get method - auto-routes based on query type"""
        analysis = await self.analyzer.analyze(query, conversation_history)
        
        self.metrics["routing_decisions"].append({
            "query": query[:50],
            "type": analysis.query_type.value,
            "confidence": analysis.confidence
        })
        
        if analysis.query_type == QueryType.STATELESS:
            # Use existing semantic cache manager
            result = await self.cache_manager.get_semantic_async(query, **kwargs)
            res_dict = {
                "hit": result is not None and result.entry is not None,
                "response": result.entry.response if result and result.entry else None,
                "routed_to": "semantic_cache",
                "query_type": "stateless"
            }
            if res_dict["hit"]: self.metrics["stateless_hits"] += 1
            return res_dict
        
        elif analysis.query_type == QueryType.CONTEXTUAL:
            if not conversation_id or not conversation_history:
                result = await self.cache_manager.get_semantic_async(query, **kwargs)
                return {
                    "hit": result is not None and result.entry is not None,
                    "response": result.entry.response if result and result.entry else None,
                    "routed_to": "semantic_cache (fallback)",
                    "query_type": "contextual_fallback"
                }
            
            result = await self.context_cache.get(query, conversation_id, conversation_history)
            result["routed_to"] = "context_cache"
            result["query_type"] = "contextual"
            if result["hit"]: self.metrics["contextual_hits"] += 1
            return result
        
        else: # AMBIGUOUS
            if conversation_id and conversation_history:
                result = await self.context_cache.get(query, conversation_id, conversation_history)
                if result["hit"]:
                    result["routed_to"] = "context_cache"
                    result["query_type"] = "ambiguous_context"
                    return result
            
            result = await self.cache_manager.get_semantic_async(query, **kwargs)
            return {
                "hit": result is not None and result.entry is not None,
                "response": result.entry.response if result and result.entry else None,
                "routed_to": "semantic_cache",
                "query_type": "ambiguous_stateless"
            }
    
    async def set(
        self,
        query: str,
        response: str,
        conversation_id: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None,
        **kwargs
    ):
        """Unified set method"""
        analysis = await self.analyzer.analyze(query, conversation_history)
        
        if analysis.query_type == QueryType.CONTEXTUAL and conversation_id:
            await self.context_cache.set(query, response, conversation_id, conversation_history)
        else:
            await self.cache_manager.put_semantic_async(query, response, **kwargs)
