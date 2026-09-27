"""College-scoped semantic subject fallback backed by a local FAISS index."""

import asyncio
import hashlib
import json
import logging
from collections import OrderedDict
from functools import lru_cache

import faiss
import numpy as np
from langchain_openai import OpenAIEmbeddings

from app.config import Settings
from app.resolvers import resolve
from app.schemas.context import RoutineContext, SubjectRecord
from app.schemas.extraction import RoutineExtraction
from app.schemas.routine import ResolvedSubject


logger = logging.getLogger(__name__)
_catalog_cache: OrderedDict[tuple, dict[str, np.ndarray]] = OrderedDict()


@lru_cache(maxsize=2)
def _local_model(name: str, cache_dir: str):
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=name, cache_dir=cache_dir)


class _LocalEmbeddings:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def aembed_documents(self, texts: list[str]):
        def embed():
            model = _local_model(self.settings.subject_local_embedding_model,
                                 self.settings.subject_local_embedding_cache_dir)
            return list(model.embed(texts))

        return await asyncio.to_thread(embed)


def _catalog_texts(subjects: list[SubjectRecord]) -> list[str]:
    return list(dict.fromkeys(
        label.strip() for item in subjects for label in (item.name, *item.aliases) if label.strip()
    ))


def _catalog_key(context: RoutineContext, settings: Settings) -> tuple:
    contents = [(item.id, item.code, item.name, item.aliases, item.category,
                 item.course, item.stream, item.semester) for item in context.subjects]
    digest = hashlib.sha256(json.dumps(contents, sort_keys=True, default=str).encode()).hexdigest()
    return (context.college_id, settings.subject_local_embedding_model,
            settings.subject_local_embedding_cache_dir, digest)


def _normalized_vectors(vectors, expected: int) -> np.ndarray:
    matrix = np.ascontiguousarray(vectors, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[0] != expected or not np.isfinite(matrix).all():
        raise ValueError("Subject embedding lookup returned an invalid batch")
    if np.any(np.linalg.norm(matrix, axis=1) == 0):
        raise ValueError("Subject embedding lookup returned a zero vector")
    faiss.normalize_L2(matrix)
    return matrix


def _build_index(candidates: list[SubjectRecord], vectors: dict[str, np.ndarray]):
    entries = [(item, label.strip()) for item in candidates
               for label in (item.name, *item.aliases) if label.strip() in vectors]
    if not entries:
        return None
    matrix = np.stack([vectors[label] for _, label in entries]).astype(np.float32)
    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    return index, entries


def _search(query: np.ndarray, scoped_index) -> list[tuple[float, SubjectRecord]]:
    if scoped_index is None:
        return []
    index, entries = scoped_index
    scores, positions = index.search(query.reshape(1, -1), len(entries))
    by_subject = {}
    for score, position in zip(scores[0], positions[0], strict=True):
        item = entries[int(position)][0]
        identity = str(item.id)
        if identity not in by_subject:
            by_subject[identity] = (float(score), item)
    return sorted(by_subject.values(), key=lambda pair: pair[0], reverse=True)


async def embedding_subject_matches(
    routines: list[RoutineExtraction], context: RoutineContext, settings: Settings,
    embedding_model=None,
) -> dict[tuple, ResolvedSubject]:
    """Search only the API catalog for this upload's college after text matching fails."""
    if embedding_model is None and settings.subject_embedding_backend == "off":
        return {}
    requests = {}
    for routine in routines:
        scoped_context = context.model_copy(update={
            "department": routine.department, "course": routine.course,
            "semester": routine.semester, "section": routine.section,
        })
        for slot in routine.slots:
            for activity in slot.activities:
                key = (routine.department, routine.course, routine.semester, routine.section,
                       activity.subject_raw, activity.subject_code_raw, activity.subject_type_raw)
                if key in requests or not activity.subject_raw or activity.subject_code_raw:
                    continue
                if resolve.subject(activity.subject_raw, None, scoped_context,
                                   activity.subject_type_raw).match_method != "unresolved":
                    continue
                candidates = resolve.scoped_subjects(scoped_context, activity.subject_raw,
                                                     activity.subject_type_raw)
                if candidates:
                    requests[key] = (activity.subject_raw, candidates)
    if not requests:
        return {}

    local = embedding_model is None and settings.subject_embedding_backend == "local"
    if embedding_model is None:
        if local:
            embedding_model = _LocalEmbeddings(settings)
        elif settings.subject_embedding_model:
            api_key = settings.subject_embedding_api_key or settings.openai_api_key
            if not api_key:
                logger.warning("Remote subject embedding model has no API key")
                return {}
            embedding_model = OpenAIEmbeddings(
                model=settings.subject_embedding_model, api_key=api_key,
                base_url=settings.subject_embedding_base_url or settings.llm_base_url,
                check_embedding_ctx_length=False, max_retries=0,
                timeout=settings.llm_timeout_seconds,
            )
        else:
            logger.warning("Remote subject embedding model is not configured")
            return {}

    catalog_texts = _catalog_texts(context.subjects)
    cache_key = _catalog_key(context, settings) if local else None
    catalog_vectors = _catalog_cache.get(cache_key) if cache_key is not None else None
    queries = list(dict.fromkeys(raw for raw, _ in requests.values()))
    texts_to_embed = ([] if catalog_vectors is not None else catalog_texts) + [
        raw for raw in queries if catalog_vectors is None or raw not in catalog_vectors
    ]
    texts_to_embed = list(dict.fromkeys(texts_to_embed))
    embedded = {}
    if texts_to_embed:
        try:
            matrix = _normalized_vectors(await embedding_model.aembed_documents(texts_to_embed),
                                         len(texts_to_embed))
        except Exception:
            logger.exception("Subject embedding lookup failed; unresolved subjects remain for review")
            return {}
        embedded = dict(zip(texts_to_embed, matrix, strict=True))
    if catalog_vectors is None:
        catalog_vectors = {name: embedded[name] for name in catalog_texts}
        if cache_key is not None:
            _catalog_cache[cache_key] = catalog_vectors
            _catalog_cache.move_to_end(cache_key)
            while len(_catalog_cache) > 4:
                _catalog_cache.popitem(last=False)
    query_vectors = {raw: embedded.get(raw, catalog_vectors.get(raw)) for raw in queries}
    minimum = (settings.subject_local_embedding_min_similarity if local
               else settings.subject_embedding_min_similarity)
    margin = (settings.subject_local_embedding_min_margin if local
              else settings.subject_embedding_min_margin)
    results = {}
    scoped_indexes = {}
    for key, (raw, candidates) in requests.items():
        scope_key = tuple(str(item.id) for item in candidates)
        if scope_key not in scoped_indexes:
            scoped_indexes[scope_key] = _build_index(candidates, catalog_vectors)
        scored = _search(query_vectors[raw], scoped_indexes[scope_key])
        if not scored:
            continue
        score, winner = scored[0]
        second = scored[1][0] if len(scored) > 1 else -1.0
        if score < minimum or score - second < margin:
            continue
        results[key] = ResolvedSubject(
            raw=raw, code_raw=None, subject_master_id=winner.id,
            code=winner.code, name=winner.name, category=winner.category,
            match_method="embedding",
        )
    return results
