#!/usr/bin/env python3
"""
Engram-Inspired Memory Enhancements

Inspired by DeepSeek's Engram architecture, this module adds:
1. O(1) hash-based fast path for repeated queries
2. Context-aware gating for memory retrieval
3. Hot cache for high-importance corrections
4. Tokenizer compression for query normalization

These enhancements sit alongside the existing memory system,
providing faster lookups without modifying core functionality.
"""

import hashlib
import re
import sqlite3
import time
import numpy as np
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class EngramConfig:
    """Configuration for Engram memory enhancements."""

    # Hash cache settings
    hash_cache_max_size: int = 10000          # Max entries in hash cache
    hash_cache_ttl_seconds: int = 3600        # Time-to-live for cache entries (1 hour)

    # Hot cache settings
    hot_cache_min_importance: int = 9         # Minimum importance for hot cache
    hot_cache_refresh_interval: int = 300     # Refresh hot cache every 5 minutes

    # Gating settings
    gating_threshold: float = 0.3             # Minimum relevance score to pass gate
    gating_decay_factor: float = 0.95         # Decay for older memories

    # Memory allocation (Engram's 75/25 split)
    max_context_tokens: int = 8000            # Max tokens for memory injection
    memory_allocation_ratio: float = 0.25     # 25% of context for memories

    # N-gram settings for hashing
    ngram_sizes: Tuple[int, ...] = (2, 3, 4)  # N-gram sizes for hash keys


# ============================================================================
# TOKENIZER COMPRESSION (Engram-style vocabulary reduction)
# ============================================================================

class TokenizerCompressor:
    """
    Compresses and normalizes text for consistent hashing.
    Inspired by Engram's 23% vocabulary reduction through canonical forms.
    """

    # Common synonyms in the codebase context
    SYNONYMS = {
        'revit': ['revit', 'autodesk revit', 'rvt', 'autodesk'],
        'wall': ['wall', 'walls', 'partition', 'partitions'],
        'create': ['create', 'make', 'build', 'generate', 'add', 'creation', 'creating', 'making', 'building'],
        'delete': ['delete', 'remove', 'destroy', 'drop', 'deletion', 'removing'],
        'error': ['error', 'bug', 'issue', 'problem', 'failure', 'errors', 'bugs', 'issues', 'problems'],
        'fix': ['fix', 'repair', 'resolve', 'correct', 'patch', 'fixing', 'fixed', 'correction'],
        'mcp': ['mcp', 'model context protocol', 'mcp server', 'mcpbridge'],
        'api': ['api', 'endpoint', 'method', 'function', 'methods', 'endpoints'],
        'memory': ['memory', 'memories', 'recall', 'remember', 'store', 'storage'],
        'view': ['view', 'views', 'viewport', 'viewports', 'sheet', 'sheets'],
        'floor': ['floor', 'level', 'story', 'floors', 'levels', 'stories'],
        'door': ['door', 'doors', 'opening', 'openings', 'doorway'],
        'window': ['window', 'windows', 'glazing'],
        'room': ['room', 'rooms', 'space', 'spaces', 'area', 'areas'],
        'project': ['project', 'projects', 'model', 'models', 'file', 'files'],
        'element': ['element', 'elements', 'object', 'objects', 'component', 'components'],
        'place': ['place', 'placement', 'placing', 'position', 'positioning', 'locate'],
        'get': ['get', 'retrieve', 'fetch', 'obtain', 'query', 'find', 'search'],
        'update': ['update', 'modify', 'change', 'edit', 'updating', 'modifying'],
        'dimension': ['dimension', 'dimensions', 'dim', 'dims', 'measurement'],
    }

    # Build reverse lookup
    _SYNONYM_MAP = {}
    for canonical, variants in SYNONYMS.items():
        for variant in variants:
            _SYNONYM_MAP[variant.lower()] = canonical

    # Stop words to remove
    STOP_WORDS = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
        'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
        'would', 'could', 'should', 'may', 'might', 'must', 'shall',
        'can', 'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by',
        'from', 'as', 'into', 'through', 'during', 'before', 'after',
        'above', 'below', 'between', 'under', 'again', 'further',
        'then', 'once', 'here', 'there', 'when', 'where', 'why',
        'how', 'all', 'each', 'few', 'more', 'most', 'other', 'some',
        'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so',
        'than', 'too', 'very', 'just', 'and', 'but', 'if', 'or',
        'because', 'until', 'while', 'this', 'that', 'these', 'those',
    }

    @classmethod
    def compress(cls, text: str) -> str:
        """
        Compress text to canonical form for consistent hashing.

        Steps:
        1. Lowercase
        2. Remove punctuation
        3. Replace synonyms with canonical forms
        4. Remove stop words
        5. Sort tokens (order-independent matching)
        """
        # Lowercase
        text = text.lower()

        # Remove punctuation except hyphens in compound words
        text = re.sub(r'[^\w\s-]', ' ', text)

        # Split into tokens
        tokens = text.split()

        # Replace synonyms and filter stop words
        canonical_tokens = []
        for token in tokens:
            # Skip stop words
            if token in cls.STOP_WORDS:
                continue

            # Skip single letters (like "i", "a" that slip through)
            if len(token) <= 1:
                continue

            # Replace with canonical form if exists
            canonical = cls._SYNONYM_MAP.get(token, token)
            canonical_tokens.append(canonical)

        # Sort for order-independent matching
        canonical_tokens.sort()

        return ' '.join(canonical_tokens)

    @classmethod
    def extract_ngrams(cls, text: str, n: int) -> List[str]:
        """Extract n-grams from compressed text."""
        compressed = cls.compress(text)
        tokens = compressed.split()

        if len(tokens) < n:
            return [compressed]

        ngrams = []
        for i in range(len(tokens) - n + 1):
            ngram = ' '.join(tokens[i:i+n])
            ngrams.append(ngram)

        return ngrams

    @classmethod
    def compute_hash(cls, text: str, ngram_sizes: Tuple[int, ...] = (2, 3, 4)) -> str:
        """
        Compute a stable hash for the text using multi-head hashing.
        Similar to Engram's multi-head hash approach.
        """
        compressed = cls.compress(text)

        # Combine hashes from different n-gram sizes
        hash_parts = []

        for n in ngram_sizes:
            ngrams = cls.extract_ngrams(text, n)
            for ngram in ngrams:
                h = hashlib.md5(ngram.encode()).hexdigest()[:8]
                hash_parts.append(h)

        # Also include full text hash
        full_hash = hashlib.md5(compressed.encode()).hexdigest()[:16]
        hash_parts.append(full_hash)

        # Combine into single hash key
        combined = '-'.join(sorted(set(hash_parts)))
        return hashlib.sha256(combined.encode()).hexdigest()[:32]


# ============================================================================
# O(1) HASH CACHE (Fast path for repeated queries)
# ============================================================================

@dataclass
class CacheEntry:
    """Single entry in the hash cache."""
    result: Any
    timestamp: float
    hit_count: int = 0


class HashCache:
    """
    O(1) lookup cache for repeated queries.
    Uses LRU eviction and TTL expiration.
    """

    def __init__(self, max_size: int = 10000, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = Lock()
        self._stats = {'hits': 0, 'misses': 0, 'evictions': 0}

    def get(self, key: str) -> Optional[Any]:
        """
        O(1) lookup. Returns None if not found or expired.
        """
        with self._lock:
            if key not in self._cache:
                self._stats['misses'] += 1
                return None

            entry = self._cache[key]

            # Check TTL
            if time.time() - entry.timestamp > self.ttl_seconds:
                del self._cache[key]
                self._stats['misses'] += 1
                return None

            # Move to end (LRU)
            self._cache.move_to_end(key)
            entry.hit_count += 1
            self._stats['hits'] += 1

            return entry.result

    def put(self, key: str, result: Any) -> None:
        """
        Store result in cache.
        """
        with self._lock:
            # Evict if at capacity
            while len(self._cache) >= self.max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                self._stats['evictions'] += 1

            self._cache[key] = CacheEntry(
                result=result,
                timestamp=time.time()
            )

    def invalidate(self, key: str) -> None:
        """Remove specific key from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]

    def clear(self) -> None:
        """Clear entire cache."""
        with self._lock:
            self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._stats['hits'] + self._stats['misses']
            hit_rate = self._stats['hits'] / total if total > 0 else 0
            return {
                **self._stats,
                'size': len(self._cache),
                'hit_rate': f"{hit_rate:.2%}"
            }


# ============================================================================
# HOT CACHE (Pre-loaded high-importance memories)
# ============================================================================

@dataclass
class HotMemory:
    """A high-importance memory kept in hot cache."""
    id: int
    content: str
    summary: str
    project: str
    importance: int
    memory_type: str
    embedding: Optional[bytes] = None


class HotCache:
    """
    In-memory cache for critical memories (corrections, high-importance).
    These are preloaded and always available with O(1) access.
    """

    def __init__(self, db_path: Path, min_importance: int = 9, refresh_interval: int = 300):
        self.db_path = db_path
        self.min_importance = min_importance
        self.refresh_interval = refresh_interval

        self._memories: Dict[int, HotMemory] = {}
        self._corrections: List[HotMemory] = []
        self._by_project: Dict[str, List[HotMemory]] = {}
        self._last_refresh: float = 0
        self._lock = Lock()

        # Initial load
        self.refresh()

    def refresh(self) -> None:
        """Reload hot memories from database."""
        with self._lock:
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Load high-importance memories
                cursor.execute("""
                    SELECT id, content, summary, project, importance, memory_type, embedding
                    FROM memories
                    WHERE importance >= ?
                    ORDER BY importance DESC, created_at DESC
                """, (self.min_importance,))

                self._memories.clear()
                self._corrections.clear()
                self._by_project.clear()

                for row in cursor.fetchall():
                    mem = HotMemory(
                        id=row['id'],
                        content=row['content'],
                        summary=row['summary'] or '',
                        project=row['project'] or '',
                        importance=row['importance'],
                        memory_type=row['memory_type'] or '',
                        embedding=row['embedding']
                    )

                    self._memories[mem.id] = mem

                    # Track corrections separately
                    if mem.memory_type == 'error' or 'correction' in mem.content.lower():
                        self._corrections.append(mem)

                    # Index by project
                    if mem.project:
                        if mem.project not in self._by_project:
                            self._by_project[mem.project] = []
                        self._by_project[mem.project].append(mem)

                conn.close()
                self._last_refresh = time.time()

            except Exception as e:
                print(f"Hot cache refresh failed: {e}")

    def _maybe_refresh(self) -> None:
        """Refresh if interval has passed."""
        if time.time() - self._last_refresh > self.refresh_interval:
            self.refresh()

    def get_corrections(self, limit: int = 10) -> List[HotMemory]:
        """Get top corrections from hot cache. O(1) access."""
        self._maybe_refresh()
        with self._lock:
            return self._corrections[:limit]

    def get_by_project(self, project: str, limit: int = 10) -> List[HotMemory]:
        """Get high-importance memories for a project. O(1) access."""
        self._maybe_refresh()
        with self._lock:
            return self._by_project.get(project, [])[:limit]

    def get_by_id(self, memory_id: int) -> Optional[HotMemory]:
        """Get specific memory if in hot cache. O(1) access."""
        self._maybe_refresh()
        with self._lock:
            return self._memories.get(memory_id)

    def get_all(self) -> List[HotMemory]:
        """Get all hot memories."""
        self._maybe_refresh()
        with self._lock:
            return list(self._memories.values())

    def get_stats(self) -> Dict[str, Any]:
        """Get hot cache statistics."""
        with self._lock:
            return {
                'total_memories': len(self._memories),
                'corrections': len(self._corrections),
                'projects': len(self._by_project),
                'last_refresh': datetime.fromtimestamp(self._last_refresh).isoformat()
            }


# ============================================================================
# CONTEXT-AWARE GATING (Filter irrelevant memories)
# ============================================================================

class ContextGate:
    """
    Gates retrieved memories based on relevance to current context.
    Inspired by Engram's context-aware gating mechanism.

    If retrieved memory conflicts with or is irrelevant to the current
    context, the gate suppresses it.
    """

    def __init__(self, threshold: float = 0.3, decay_factor: float = 0.95):
        self.threshold = threshold
        self.decay_factor = decay_factor

    def compute_relevance(
        self,
        memory_embedding: np.ndarray,
        context_embedding: np.ndarray,
        memory_age_days: float,
        memory_importance: int,
        memory_access_count: int
    ) -> float:
        """
        Compute relevance score for a memory given current context.

        Factors:
        1. Semantic similarity (embedding cosine similarity)
        2. Recency decay (older memories score lower)
        3. Importance boost (high importance memories score higher)
        4. Access frequency (frequently accessed = more relevant)
        """
        # Base: cosine similarity
        if memory_embedding is not None and context_embedding is not None:
            similarity = np.dot(memory_embedding, context_embedding) / (
                np.linalg.norm(memory_embedding) * np.linalg.norm(context_embedding)
            )
        else:
            similarity = 0.5  # Neutral if no embeddings

        # Recency decay
        recency_score = self.decay_factor ** memory_age_days

        # Importance boost (normalize to 0-1)
        importance_score = memory_importance / 10.0

        # Access frequency boost (diminishing returns)
        access_score = min(1.0, np.log1p(memory_access_count) / 5)

        # Weighted combination
        relevance = (
            0.5 * similarity +          # Semantic relevance is most important
            0.2 * recency_score +       # Recent memories preferred
            0.2 * importance_score +    # Important memories preferred
            0.1 * access_score          # Frequently accessed preferred
        )

        return float(relevance)

    def gate(
        self,
        memories: List[Dict[str, Any]],
        context_embedding: Optional[np.ndarray],
        context_project: Optional[str] = None
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Apply gating to filter and rank memories.

        Returns list of (memory, relevance_score) tuples sorted by relevance.
        Memories below threshold are filtered out.
        """
        scored_memories = []

        for memory in memories:
            # Extract embedding if present
            mem_embedding = None
            if memory.get('embedding'):
                try:
                    mem_embedding = np.frombuffer(memory['embedding'], dtype=np.float32)
                except:
                    pass

            # Calculate age in days
            created_at = memory.get('created_at', '')
            try:
                if isinstance(created_at, str):
                    created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                else:
                    created_dt = created_at
                age_days = (datetime.now() - created_dt.replace(tzinfo=None)).days
            except:
                age_days = 30  # Default to 30 days if can't parse

            # Compute relevance
            relevance = self.compute_relevance(
                memory_embedding=mem_embedding,
                context_embedding=context_embedding,
                memory_age_days=age_days,
                memory_importance=memory.get('importance', 5),
                memory_access_count=memory.get('access_count', 0)
            )

            # Project match boost
            if context_project and memory.get('project') == context_project:
                relevance = min(1.0, relevance * 1.3)  # 30% boost for same project

            # Apply gate
            if relevance >= self.threshold:
                scored_memories.append((memory, relevance))

        # Sort by relevance descending
        scored_memories.sort(key=lambda x: x[1], reverse=True)

        return scored_memories


# ============================================================================
# ENGRAM MEMORY SYSTEM (Main integration class)
# ============================================================================

class EngramMemory:
    """
    Main class integrating all Engram-inspired enhancements.

    Usage:
        engram = EngramMemory(db_path)

        # Fast recall with caching
        result = engram.recall("wall creation revit")

        # Gated retrieval
        memories = engram.recall_gated(query, context_embedding, project)

        # Access corrections instantly
        corrections = engram.get_corrections()
    """

    def __init__(self, db_path: Path, config: EngramConfig = None):
        self.db_path = db_path
        self.config = config or EngramConfig()

        # Initialize components
        self.compressor = TokenizerCompressor()
        self.hash_cache = HashCache(
            max_size=self.config.hash_cache_max_size,
            ttl_seconds=self.config.hash_cache_ttl_seconds
        )
        self.hot_cache = HotCache(
            db_path=db_path,
            min_importance=self.config.hot_cache_min_importance,
            refresh_interval=self.config.hot_cache_refresh_interval
        )
        self.gate = ContextGate(
            threshold=self.config.gating_threshold,
            decay_factor=self.config.gating_decay_factor
        )

    def recall(self, query: str, project: str = None, limit: int = 10) -> Dict[str, Any]:
        """
        Enhanced recall with O(1) hash cache fast path.

        Flow:
        1. Compress query
        2. Check hash cache (O(1))
        3. If miss, query database
        4. Cache result
        """
        # Compress and hash query
        compressed = self.compressor.compress(query)
        cache_key = self.compressor.compute_hash(
            f"{query}:{project or ''}:{limit}",
            self.config.ngram_sizes
        )

        # Check hash cache (O(1) fast path)
        cached = self.hash_cache.get(cache_key)
        if cached is not None:
            return {
                'source': 'hash_cache',
                'results': cached,
                'compressed_query': compressed
            }

        # Check hot cache for corrections first
        hot_corrections = self.hot_cache.get_corrections(limit=3)
        hot_project = self.hot_cache.get_by_project(project, limit=3) if project else []

        # Query database (slow path)
        results = self._query_database(query, project, limit)

        # Merge hot cache results (they always appear first)
        hot_results = []
        for hm in hot_corrections + hot_project:
            hot_results.append({
                'id': hm.id,
                'content': hm.content,
                'summary': hm.summary,
                'project': hm.project,
                'importance': hm.importance,
                'memory_type': hm.memory_type,
                'source': 'hot_cache'
            })

        # Deduplicate
        seen_ids = {r['id'] for r in hot_results}
        for r in results:
            if r['id'] not in seen_ids:
                hot_results.append(r)

        final_results = hot_results[:limit]

        # Cache the result
        self.hash_cache.put(cache_key, final_results)

        return {
            'source': 'database',
            'results': final_results,
            'compressed_query': compressed
        }

    def recall_gated(
        self,
        query: str,
        context_embedding: np.ndarray = None,
        project: str = None,
        limit: int = 10
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Recall with context-aware gating.

        Returns memories filtered and ranked by relevance to current context.
        """
        # Get raw results
        raw = self.recall(query, project, limit * 2)  # Get more to allow for filtering

        # Apply gating
        gated = self.gate.gate(
            memories=raw['results'],
            context_embedding=context_embedding,
            context_project=project
        )

        return gated[:limit]

    def get_corrections(self, limit: int = 10) -> List[HotMemory]:
        """Direct O(1) access to corrections from hot cache."""
        return self.hot_cache.get_corrections(limit)

    def get_hot_memories(self, project: str = None) -> List[HotMemory]:
        """Get high-importance memories, optionally filtered by project."""
        if project:
            return self.hot_cache.get_by_project(project)
        return self.hot_cache.get_all()

    def invalidate_cache(self, memory_id: int = None) -> None:
        """
        Invalidate caches when data changes.
        Call this after memory_store or memory_forget.
        """
        if memory_id:
            # Could track which cache keys reference this memory
            # For now, just clear the hash cache
            pass
        self.hash_cache.clear()
        self.hot_cache.refresh()

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics."""
        return {
            'hash_cache': self.hash_cache.get_stats(),
            'hot_cache': self.hot_cache.get_stats(),
            'config': {
                'hash_cache_max_size': self.config.hash_cache_max_size,
                'hash_cache_ttl_seconds': self.config.hash_cache_ttl_seconds,
                'gating_threshold': self.config.gating_threshold,
                'memory_allocation_ratio': self.config.memory_allocation_ratio
            }
        }

    def _query_database(self, query: str, project: str, limit: int) -> List[Dict[str, Any]]:
        """Query the underlying database."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Use FTS5 search
            sql = """
                SELECT
                    m.id, m.content, m.summary, m.project, m.tags,
                    m.importance, m.memory_type, m.created_at,
                    m.access_count, m.embedding
                FROM memories_fts
                JOIN memories m ON memories_fts.rowid = m.id
                WHERE memories_fts MATCH ?
            """
            params = [query]

            if project:
                sql += " AND m.project = ?"
                params.append(project)

            sql += " ORDER BY bm25(memories_fts) LIMIT ?"
            params.append(limit)

            cursor.execute(sql, params)

            results = []
            for row in cursor.fetchall():
                results.append(dict(row))

            conn.close()
            return results

        except Exception as e:
            print(f"Database query failed: {e}")
            return []


# ============================================================================
# INTEGRATION WITH EXISTING SERVER
# ============================================================================

# Global instance (lazy initialization)
_engram_instance: Optional[EngramMemory] = None

def get_engram(db_path: Path = None) -> EngramMemory:
    """Get or create the global Engram instance."""
    global _engram_instance

    if _engram_instance is None:
        if db_path is None:
            # Default path
            db_path = Path(__file__).parent.parent / "data" / "memories.db"
        _engram_instance = EngramMemory(db_path)

    return _engram_instance


def engram_recall(query: str, project: str = None, limit: int = 10) -> Dict[str, Any]:
    """
    Enhanced recall function that can replace memory_recall.
    Uses hash cache for O(1) repeated queries.
    """
    return get_engram().recall(query, project, limit)


def engram_recall_gated(
    query: str,
    context_embedding: np.ndarray = None,
    project: str = None,
    limit: int = 10
) -> List[Tuple[Dict[str, Any], float]]:
    """
    Gated recall that filters by context relevance.
    """
    return get_engram().recall_gated(query, context_embedding, project, limit)


def engram_get_corrections(limit: int = 10) -> List[Dict[str, Any]]:
    """
    O(1) access to corrections from hot cache.
    """
    corrections = get_engram().get_corrections(limit)
    return [
        {
            'id': c.id,
            'content': c.content,
            'summary': c.summary,
            'project': c.project,
            'importance': c.importance
        }
        for c in corrections
    ]


def engram_stats() -> Dict[str, Any]:
    """Get Engram enhancement statistics."""
    return get_engram().get_stats()


def engram_invalidate():
    """Invalidate caches after data changes."""
    get_engram().invalidate_cache()


# ============================================================================
# CLI FOR TESTING
# ============================================================================

if __name__ == "__main__":
    import sys

    # Initialize with default path
    db_path = Path(__file__).parent.parent / "data" / "memories.db"

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        sys.exit(1)

    engram = EngramMemory(db_path)

    print("=" * 60)
    print("ENGRAM MEMORY ENHANCEMENT TEST")
    print("=" * 60)

    # Test compression
    test_queries = [
        "How do I create walls in Revit?",
        "how to CREATE WALLS in revit",  # Should compress to same
        "wall creation revit",
        "Revit wall making",
    ]

    print("\n1. TOKENIZER COMPRESSION")
    print("-" * 40)
    for q in test_queries:
        compressed = TokenizerCompressor.compress(q)
        hash_key = TokenizerCompressor.compute_hash(q)
        print(f"Query: {q}")
        print(f"  Compressed: {compressed}")
        print(f"  Hash: {hash_key[:16]}...")
        print()

    # Test hot cache
    print("\n2. HOT CACHE")
    print("-" * 40)
    stats = engram.hot_cache.get_stats()
    print(f"Hot cache loaded: {stats}")

    corrections = engram.get_corrections(5)
    print(f"\nTop {len(corrections)} corrections in hot cache:")
    for c in corrections[:3]:
        print(f"  [{c.id}] {c.summary[:60]}...")

    # Test hash cache
    print("\n3. HASH CACHE PERFORMANCE")
    print("-" * 40)

    test_query = "wall creation"

    # First call (miss)
    start = time.time()
    result1 = engram.recall(test_query)
    time1 = time.time() - start
    print(f"First call (cache miss): {time1*1000:.2f}ms, source={result1['source']}")

    # Second call (hit)
    start = time.time()
    result2 = engram.recall(test_query)
    time2 = time.time() - start
    print(f"Second call (cache hit): {time2*1000:.2f}ms, source={result2['source']}")

    if time1 > 0:
        print(f"Speedup: {time1/max(time2, 0.0001):.1f}x faster")

    # Overall stats
    print("\n4. OVERALL STATISTICS")
    print("-" * 40)
    stats = engram.get_stats()
    print(f"Hash cache: {stats['hash_cache']}")
    print(f"Hot cache: {stats['hot_cache']}")

    print("\n" + "=" * 60)
    print("Test complete!")
