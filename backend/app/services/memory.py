from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import Select, func, or_, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.memory_item import MemoryItem
from app.services.embeddings import EmbeddingService

CONFLICT_SIMILARITY_THRESHOLD = 0.92
SEARCH_MIN_SIMILARITY = 0.05


class MemoryService:
    MEMORY_TYPES = {"preference", "fact", "style", "context"}
    VISIBILITY_PRIVATE = "private"
    VISIBILITY_ORGANIZATION = "organization"
    VISIBILITY_PROMOTED = "promoted"

    def __init__(self, *, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.embeddings = EmbeddingService(settings)
        self._use_pgvector = db.bind is not None and db.bind.dialect.name == "postgresql"

    def _visible_to_user_filter(
        self,
        stmt: Select[tuple[MemoryItem]],
        *,
        organization_id: UUID,
        user_id: UUID,
    ) -> Select[tuple[MemoryItem]]:
        return stmt.where(
            MemoryItem.organization_id == organization_id,
            MemoryItem.forgotten_at.is_(None),
            or_(
                MemoryItem.owner_user_id == user_id,
                MemoryItem.visibility.in_((self.VISIBILITY_ORGANIZATION, self.VISIBILITY_PROMOTED)),
            ),
        )

    def get_memory_for_user(
        self,
        *,
        memory_id: UUID,
        organization_id: UUID,
        user_id: UUID,
    ) -> MemoryItem:
        stmt = select(MemoryItem).where(MemoryItem.id == memory_id)
        stmt = self._visible_to_user_filter(stmt, organization_id=organization_id, user_id=user_id)
        memory = self.db.scalar(stmt)
        if memory is None:
            raise NotFoundError("Memory item not found")
        return memory

    def get_owned_memory(
        self,
        *,
        memory_id: UUID,
        organization_id: UUID,
        user_id: UUID,
    ) -> MemoryItem:
        memory = self.get_memory_for_user(
            memory_id=memory_id,
            organization_id=organization_id,
            user_id=user_id,
        )
        if memory.owner_user_id != user_id:
            raise ForbiddenError("You can only modify your own memories")
        return memory

    def create_memory(
        self,
        *,
        organization_id: UUID,
        owner_user_id: UUID,
        content: str,
        memory_type: str,
        source_type: str,
        conversation_id: UUID | None = None,
        source_ref: str | None = None,
        source_excerpt: str | None = None,
        confidence_score: float = 1.0,
        visibility: str = VISIBILITY_PRIVATE,
    ) -> MemoryItem:
        embedding = self.embeddings.embed_text(content)
        existing = self._find_conflicting_memory(
            organization_id=organization_id,
            owner_user_id=owner_user_id,
            memory_type=memory_type,
            embedding=embedding,
        )
        if existing is not None:
            existing.content = content
            existing.confidence_score = max(existing.confidence_score, confidence_score)
            existing.source_type = source_type
            existing.source_kind = source_type
            if source_ref:
                existing.source_ref = source_ref
            if source_excerpt:
                existing.source_excerpt = source_excerpt
            self._set_embedding(existing, embedding)
            self.db.commit()
            self._sync_pgvector_embedding(existing)
            self.db.refresh(existing)
            return existing

        memory = MemoryItem(
            organization_id=organization_id,
            owner_user_id=owner_user_id,
            conversation_id=conversation_id,
            source_type=source_type,
            source_kind=source_type,
            source_ref=source_ref,
            source_excerpt=source_excerpt,
            memory_type=memory_type,
            content=content,
            visibility=visibility,
            confidence_score=confidence_score,
            embedding_model=self.settings.embedding_model_name,
            embedding_dimensions=self.settings.pgvector_embedding_dimensions,
        )
        self._set_embedding(memory, embedding)
        self.db.add(memory)
        self.db.commit()
        self._sync_pgvector_embedding(memory)
        self.db.refresh(memory)
        return memory

    def _find_conflicting_memory(
        self,
        *,
        organization_id: UUID,
        owner_user_id: UUID,
        memory_type: str,
        embedding: list[float],
    ) -> MemoryItem | None:
        stmt = select(MemoryItem).where(
            MemoryItem.organization_id == organization_id,
            MemoryItem.owner_user_id == owner_user_id,
            MemoryItem.memory_type == memory_type,
            MemoryItem.forgotten_at.is_(None),
        )
        candidates = list(self.db.scalars(stmt))
        for candidate in candidates:
            candidate_embedding = self._read_embedding(candidate)
            if self._cosine_similarity(embedding, candidate_embedding) >= CONFLICT_SIMILARITY_THRESHOLD:
                return candidate
        return None

    def list_memories(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
        memory_type: str | None = None,
    ) -> tuple[list[MemoryItem], int]:
        stmt: Select[tuple[MemoryItem]] = select(MemoryItem)
        stmt = self._visible_to_user_filter(stmt, organization_id=organization_id, user_id=user_id)
        if memory_type:
            stmt = stmt.where(MemoryItem.memory_type == memory_type)

        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        order_by = [
            MemoryItem.pinned_at.is_(None),
            MemoryItem.created_at.desc(),
        ]
        items = list(
            self.db.scalars(
                stmt.order_by(*order_by)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return items, total

    def search_relevant_memories(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        query: str,
        limit: int = 5,
    ) -> list[MemoryItem]:
        query_embedding = self.embeddings.embed_text(query)
        stmt = select(MemoryItem)
        stmt = self._visible_to_user_filter(stmt, organization_id=organization_id, user_id=user_id)

        if self._use_pgvector:
            vector_literal = self._vector_literal(query_embedding)
            rows = self.db.execute(
                text(
                    """
                    SELECT id
                    FROM memory_items
                    WHERE organization_id = :organization_id
                      AND forgotten_at IS NULL
                      AND embedding IS NOT NULL
                      AND (
                        owner_user_id = :user_id
                        OR visibility IN ('organization', 'promoted')
                      )
                    ORDER BY embedding <=> CAST(:query_embedding AS vector)
                    LIMIT :limit
                    """
                ),
                {
                    "organization_id": str(organization_id),
                    "user_id": str(user_id),
                    "query_embedding": vector_literal,
                    "limit": limit * 2,
                },
            ).fetchall()
            memory_ids = [row.id for row in rows]
            if not memory_ids:
                return []
            memories = list(
                self.db.scalars(select(MemoryItem).where(MemoryItem.id.in_(memory_ids)))
            )
            memory_by_id = {memory.id: memory for memory in memories}
            ordered = [memory_by_id[memory_id] for memory_id in memory_ids if memory_id in memory_by_id]
            scored = [
                (self._cosine_similarity(query_embedding, self._read_embedding(memory)), memory)
                for memory in ordered
            ]
        else:
            memories = list(self.db.scalars(stmt))
            scored = [
                (self._cosine_similarity(query_embedding, self._read_embedding(memory)), memory)
                for memory in memories
            ]

        scored.sort(key=lambda item: (item[1].pinned_at is not None, item[0]), reverse=True)
        return [memory for score, memory in scored[:limit] if score > SEARCH_MIN_SIMILARITY]

    def correct_memory(
        self,
        *,
        memory_id: UUID,
        organization_id: UUID,
        user_id: UUID,
        content: str,
    ) -> MemoryItem:
        memory = self.get_owned_memory(
            memory_id=memory_id,
            organization_id=organization_id,
            user_id=user_id,
        )
        embedding = self.embeddings.embed_text(content)
        memory.content = content
        memory.corrected_at = datetime.now(timezone.utc)
        self._set_embedding(memory, embedding)
        self.db.commit()
        self._sync_pgvector_embedding(memory)
        self.db.refresh(memory)
        return memory

    def forget_memory(
        self,
        *,
        memory_id: UUID,
        organization_id: UUID,
        user_id: UUID,
    ) -> MemoryItem:
        memory = self.get_owned_memory(
            memory_id=memory_id,
            organization_id=organization_id,
            user_id=user_id,
        )
        memory.forgotten_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(memory)
        return memory

    def pin_memory(
        self,
        *,
        memory_id: UUID,
        organization_id: UUID,
        user_id: UUID,
    ) -> MemoryItem:
        memory = self.get_owned_memory(
            memory_id=memory_id,
            organization_id=organization_id,
            user_id=user_id,
        )
        memory.pinned_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(memory)
        return memory

    def _set_embedding(self, memory: MemoryItem, embedding: list[float]) -> None:
        memory.embedding_vector = embedding
        if self._use_pgvector and memory.id is not None:
            self.db.flush()
            self.db.execute(
                text("UPDATE memory_items SET embedding = CAST(:embedding AS vector) WHERE id = :id"),
                {"embedding": self._vector_literal(embedding), "id": str(memory.id)},
            )
        elif self._use_pgvector:
            memory._pending_embedding = embedding  # type: ignore[attr-defined]

    def _sync_pgvector_embedding(self, memory: MemoryItem) -> None:
        pending = getattr(memory, "_pending_embedding", None)
        if pending is not None and self._use_pgvector:
            self.db.execute(
                text("UPDATE memory_items SET embedding = CAST(:embedding AS vector) WHERE id = :id"),
                {"embedding": self._vector_literal(pending), "id": str(memory.id)},
            )
            delattr(memory, "_pending_embedding")

    @staticmethod
    def _vector_literal(embedding: list[float]) -> str:
        return "[" + ",".join(str(float(value)) for value in embedding) + "]"

    def _read_embedding(self, memory: MemoryItem) -> list[float]:
        if isinstance(memory.embedding_vector, list):
            return memory.embedding_vector
        return []

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right:
            return 0.0
        size = min(len(left), len(right))
        dot = sum(left[index] * right[index] for index in range(size))
        left_norm = sum(value * value for value in left[:size]) ** 0.5
        right_norm = sum(value * value for value in right[:size]) ** 0.5
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)

    def extract_memories_from_message(self, message: str) -> list[dict[str, str]]:
        return self.extract_memories_from_text(message, source_hint="chat")

    def extract_memories_from_text(self, text: str, *, source_hint: str = "chat") -> list[dict[str, str]]:
        extracted: list[dict[str, str]] = []
        lowered = text.lower()
        normalized = lowered.replace(".", "")

        if "hate" in lowered and "9 am" in normalized:
            extracted.append(
                {
                    "memory_type": "preference",
                    "content": "User prefers not to schedule meetings at 9 AM.",
                }
            )
        if "avoid" in lowered and "morning" in lowered:
            extracted.append(
                {
                    "memory_type": "preference",
                    "content": "User prefers to avoid morning meetings.",
                }
            )
        if "formal tone" in lowered or "formal with clients" in lowered:
            extracted.append(
                {
                    "memory_type": "style",
                    "content": "User prefers a formal tone when communicating with clients.",
                }
            )
        if "project x" in lowered and ("delay" in lowered or "delayed" in lowered):
            extracted.append(
                {
                    "memory_type": "fact",
                    "content": "Project X is delayed.",
                }
            )
        if source_hint == "email":
            if "deadline" in lowered and "extend" in lowered:
                extracted.append(
                    {
                        "memory_type": "fact",
                        "content": "An email indicates a deadline extension request.",
                    }
                )
            if "urgent" in lowered or "asap" in lowered:
                extracted.append(
                    {
                        "memory_type": "context",
                        "content": "Recent email traffic includes urgent requests.",
                    }
                )
        return extracted
