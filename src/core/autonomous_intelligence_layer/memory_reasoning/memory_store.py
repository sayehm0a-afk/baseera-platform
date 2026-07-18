"""
Memory Store Module

This module implements the Memory Store, which manages different types of memory
(working, short-term, episodic, semantic, procedural, long-term) with operations
for storing, retrieving, searching, ranking, summarizing, consolidating, and
expiring memory entries.
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from enum import Enum
import logging
import json


logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """Enumeration for different types of memory."""
    WORKING = "working"  # Current task context
    SHORT_TERM = "short_term"  # Recent information (minutes to hours)
    EPISODIC = "episodic"  # Specific events and experiences
    SEMANTIC = "semantic"  # Facts and concepts
    PROCEDURAL = "procedural"  # How to do things
    LONG_TERM = "long_term"  # Important information for long-term retention


@dataclass
class MemoryEntry:
    """Represents a single memory entry."""
    memory_id: str
    memory_type: MemoryType
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: Optional[str] = None
    confidence: float = 1.0  # 0.0 to 1.0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    expiration_time: Optional[datetime] = None
    is_archived: bool = False


@dataclass
class MemoryStoreConfig:
    """Configuration for Memory Store."""
    max_working_memory_entries: int = 100
    max_short_term_memory_entries: int = 1000
    max_episodic_memory_entries: int = 5000
    max_semantic_memory_entries: int = 10000
    max_procedural_memory_entries: int = 1000
    max_long_term_memory_entries: int = 50000
    short_term_memory_ttl_hours: int = 24
    episodic_memory_ttl_days: int = 30
    semantic_memory_ttl_days: int = 365
    procedural_memory_ttl_days: int = 365
    long_term_memory_ttl_days: int = 3650  # 10 years
    enable_deduplication: bool = True
    enable_consolidation: bool = True
    enable_archival: bool = True


class MemoryStore:
    """
    Memory Store for managing different types of memory.

    The Memory Store is responsible for:
    - Storing information in appropriate memory types
    - Retrieving information based on queries
    - Searching and ranking memory entries
    - Summarizing and consolidating information
    - Expiring and archiving old information
    - Applying access controls
    """

    def __init__(self, config: Optional[MemoryStoreConfig] = None):
        """
        Initialize the Memory Store.

        Args:
            config: MemoryStoreConfig instance for configuring memory behavior.
                   If None, uses default config.
        """
        self.config = config or MemoryStoreConfig()
        self.memory: Dict[MemoryType, List[MemoryEntry]] = {
            memory_type: [] for memory_type in MemoryType
        }
        self.memory_index: Dict[str, MemoryEntry] = {}  # Index by memory_id

    def store(
        self,
        content: str,
        memory_type: MemoryType,
        source: Optional[str] = None,
        confidence: float = 1.0,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryEntry:
        """
        Store information in memory.

        Args:
            content: The content to store
            memory_type: The type of memory to store in
            source: Optional source of the information
            confidence: Confidence level (0.0 to 1.0)
            tags: Optional tags for categorization
            metadata: Optional additional metadata

        Returns:
            MemoryEntry representing the stored information
        """
        memory_id = f"{memory_type.value}_{datetime.now(UTC).timestamp()}"

        # Create memory entry
        entry = MemoryEntry(
            memory_id=memory_id,
            memory_type=memory_type,
            content=content,
            source=source,
            confidence=max(0.0, min(1.0, confidence)),
            tags=tags or [],
            metadata=metadata or {},
            expiration_time=self._calculate_expiration_time(memory_type),
        )

        # Check for duplicates if deduplication is enabled
        if self.config.enable_deduplication:
            if self._is_duplicate(entry):
                logger.debug(f"Duplicate memory entry detected: {memory_id}")
                return entry

        # Add to memory
        self.memory[memory_type].append(entry)
        self.memory_index[memory_id] = entry

        # Enforce size limits
        self._enforce_size_limits(memory_type)

        logger.debug(f"Memory entry stored: {memory_id}")
        return entry

    def retrieve(
        self,
        memory_type: MemoryType,
        limit: int = 10,
    ) -> List[MemoryEntry]:
        """
        Retrieve memory entries of a specific type.

        Args:
            memory_type: The type of memory to retrieve
            limit: Maximum number of entries to retrieve

        Returns:
            List of MemoryEntry objects
        """
        entries = self.memory[memory_type]

        # Filter out archived and expired entries
        active_entries = [
            e for e in entries
            if not e.is_archived and not self._is_expired(e)
        ]

        # Sort by access count (most accessed first)
        sorted_entries = sorted(
            active_entries,
            key=lambda e: e.access_count,
            reverse=True,
        )

        # Update access information
        for entry in sorted_entries[:limit]:
            entry.access_count += 1
            entry.last_accessed = datetime.now(UTC)

        return sorted_entries[:limit]

    def search(
        self,
        query: str,
        memory_types: Optional[List[MemoryType]] = None,
        limit: int = 10,
    ) -> List[MemoryEntry]:
        """
        Search for memory entries matching a query.

        Args:
            query: Search query
            memory_types: Optional list of memory types to search in
            limit: Maximum number of results

        Returns:
            List of matching MemoryEntry objects
        """
        if memory_types is None:
            memory_types = list(MemoryType)

        results = []
        query_lower = query.lower()

        for memory_type in memory_types:
            entries = self.memory[memory_type]
            for entry in entries:
                if (not entry.is_archived and not self._is_expired(entry) and
                    query_lower in entry.content.lower()):
                    results.append(entry)

        # Sort by confidence and relevance
        sorted_results = sorted(
            results,
            key=lambda e: e.confidence,
            reverse=True,
        )

        # Update access information
        for entry in sorted_results[:limit]:
            entry.access_count += 1
            entry.last_accessed = datetime.now(UTC)

        return sorted_results[:limit]

    def rank(
        self,
        entries: List[MemoryEntry],
        criteria: Optional[Dict[str, float]] = None,
    ) -> List[MemoryEntry]:
        """
        Rank memory entries based on criteria.

        Args:
            entries: List of memory entries to rank
            criteria: Optional ranking criteria (confidence, recency, access_count)

        Returns:
            Ranked list of MemoryEntry objects
        """
        if criteria is None:
            criteria = {
                "confidence": 0.5,
                "recency": 0.3,
                "access_count": 0.2,
            }

        def calculate_score(entry: MemoryEntry) -> float:
            score = 0.0

            if "confidence" in criteria:
                score += entry.confidence * criteria["confidence"]

            if "recency" in criteria:
                age_days = (datetime.now(UTC) - entry.timestamp).days
                recency_score = max(0.0, 1.0 - (age_days / 365.0))
                score += recency_score * criteria["recency"]

            if "access_count" in criteria:
                # Normalize access count (assuming max 1000 accesses)
                access_score = min(1.0, entry.access_count / 1000.0)
                score += access_score * criteria["access_count"]

            return score

        ranked_entries = sorted(
            entries,
            key=calculate_score,
            reverse=True,
        )
        return ranked_entries

    def summarize(
        self,
        entries: List[MemoryEntry],
        max_summary_length: int = 500,
    ) -> str:
        """
        Summarize a list of memory entries.

        Args:
            entries: List of memory entries to summarize
            max_summary_length: Maximum length of the summary

        Returns:
            Summary string
        """
        if not entries:
            return "No memory entries to summarize."

        # Simple summarization: concatenate content with ellipsis
        summary_parts = []
        current_length = 0

        for entry in entries:
            if current_length + len(entry.content) <= max_summary_length:
                summary_parts.append(entry.content)
                current_length += len(entry.content) + 2  # +2 for separator
            else:
                break

        summary = " | ".join(summary_parts)
        if len(summary) > max_summary_length:
            summary = summary[:max_summary_length] + "..."

        return summary

    def consolidate(self, memory_type: MemoryType) -> None:
        """
        Consolidate memory entries (remove duplicates, merge similar entries).

        Args:
            memory_type: The type of memory to consolidate
        """
        entries = self.memory[memory_type]

        # Remove duplicates
        unique_entries = []
        seen_content = set()

        for entry in entries:
            if entry.content not in seen_content:
                unique_entries.append(entry)
                seen_content.add(entry.content)

        self.memory[memory_type] = unique_entries
        logger.debug(f"Consolidated {memory_type.value} memory")

    def expire(self) -> None:
        """Expire and archive old memory entries."""
        for memory_type in MemoryType:
            entries = self.memory[memory_type]

            for entry in entries:
                if self._is_expired(entry) and not entry.is_archived:
                    if self.config.enable_archival:
                        entry.is_archived = True
                    else:
                        # Remove from memory
                        entries.remove(entry)
                        if entry.memory_id in self.memory_index:
                            del self.memory_index[entry.memory_id]

        logger.debug("Expired old memory entries")

    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get statistics about memory usage.

        Returns:
            Dictionary containing memory statistics
        """
        stats = {}
        total_entries = 0

        for memory_type in MemoryType:
            entries = self.memory[memory_type]
            active_entries = [
                e for e in entries
                if not e.is_archived and not self._is_expired(e)
            ]
            stats[memory_type.value] = {
                "total_entries": len(entries),
                "active_entries": len(active_entries),
                "archived_entries": len([e for e in entries if e.is_archived]),
            }
            total_entries += len(active_entries)

        stats["total_active_entries"] = total_entries
        return stats

    def _calculate_expiration_time(self, memory_type: MemoryType) -> Optional[datetime]:
        """Calculate expiration time based on memory type."""
        now = datetime.now(UTC)

        if memory_type == MemoryType.WORKING:
            return None  # Working memory doesn't expire
        elif memory_type == MemoryType.SHORT_TERM:
            return now + timedelta(hours=self.config.short_term_memory_ttl_hours)
        elif memory_type == MemoryType.EPISODIC:
            return now + timedelta(days=self.config.episodic_memory_ttl_days)
        elif memory_type == MemoryType.SEMANTIC:
            return now + timedelta(days=self.config.semantic_memory_ttl_days)
        elif memory_type == MemoryType.PROCEDURAL:
            return now + timedelta(days=self.config.procedural_memory_ttl_days)
        elif memory_type == MemoryType.LONG_TERM:
            return now + timedelta(days=self.config.long_term_memory_ttl_days)

        return None

    def _is_expired(self, entry: MemoryEntry) -> bool:
        """Check if a memory entry has expired."""
        if entry.expiration_time is None:
            return False
        return datetime.now(UTC) > entry.expiration_time

    def _is_duplicate(self, entry: MemoryEntry) -> bool:
        """Check if a memory entry is a duplicate."""
        for existing_entry in self.memory[entry.memory_type]:
            if existing_entry.content == entry.content:
                return True
        return False

    def _enforce_size_limits(self, memory_type: MemoryType) -> None:
        """Enforce size limits for memory types."""
        max_entries = {
            MemoryType.WORKING: self.config.max_working_memory_entries,
            MemoryType.SHORT_TERM: self.config.max_short_term_memory_entries,
            MemoryType.EPISODIC: self.config.max_episodic_memory_entries,
            MemoryType.SEMANTIC: self.config.max_semantic_memory_entries,
            MemoryType.PROCEDURAL: self.config.max_procedural_memory_entries,
            MemoryType.LONG_TERM: self.config.max_long_term_memory_entries,
        }

        entries = self.memory[memory_type]
        if len(entries) > max_entries[memory_type]:
            # Remove oldest entries
            entries.sort(key=lambda e: e.timestamp)
            to_remove = len(entries) - max_entries[memory_type]

            for entry in entries[:to_remove]:
                if entry.memory_id in self.memory_index:
                    del self.memory_index[entry.memory_id]

            self.memory[memory_type] = entries[to_remove:]
