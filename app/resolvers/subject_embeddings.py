"""Optional batch semantic fallback for otherwise unresolved subject names."""

import logging
import math

from langchain_openai import OpenAIEmbeddings

from app.config import Settings
from app.resolvers import resolve
from app.schemas.context import RoutineContext
from app.schemas.extraction import RoutineExtraction
from app.schemas.routine import ResolvedSubject


logger = logging.getLogger(__name__)


def _cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    magnitude = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    return numerator / magnitude if magnitude else 0.0


async def embedding_subject_matches(
    routines: list[RoutineExtraction], context: RoutineContext, settings: Settings,
    embedding_model=None,
) -> dict[tuple, ResolvedSubject]:
    """Embed subjects and queries once per upload; never override a known code."""
    if not settings.subject_embedding_model and embedding_model is None:
        return {}
    requests = {}
    for routine in routines:
        scoped_context = context.model_copy(update={
            "department": routine.department, "course": routine.course,
            "semester": routine.semester, "section": routine.section,
        })
        for slot in routine.slots:
            for activity in slot.activities:
                key = (routine.department, routine.course, routine.semester,
                       activity.subject_raw, activity.subject_code_raw)
                if key in requests or not activity.subject_raw or activity.subject_code_raw:
                    continue
                if resolve.subject(activity.subject_raw, activity.subject_code_raw, scoped_context).match_method != "unresolved":
                    continue
                candidates = resolve.scoped_subjects(scoped_context)
                if candidates:
                    requests[key] = (activity.subject_raw, candidates)
    if not requests:
        return {}

    names = list(dict.fromkeys(item.name for _, candidates in requests.values() for item in candidates))
    queries = list(dict.fromkeys(raw for raw, _ in requests.values()))
    if embedding_model is None:
        api_key = settings.subject_embedding_api_key or settings.openai_api_key
        if not api_key:
            logger.warning("Subject embedding model is configured without an API key")
            return {}
        embedding_model = OpenAIEmbeddings(
            model=settings.subject_embedding_model, api_key=api_key,
            base_url=settings.subject_embedding_base_url or settings.llm_base_url,
            check_embedding_ctx_length=False, max_retries=0,
            timeout=settings.llm_timeout_seconds,
        )
    try:
        vectors = await embedding_model.aembed_documents(names + queries)
    except Exception:
        logger.exception("Subject embedding lookup failed; unresolved subjects remain for review")
        return {}
    if len(vectors) != len(names) + len(queries) or not vectors:
        logger.warning("Subject embedding lookup returned an incomplete batch")
        return {}
    indexed = {name: vectors[index] for index, name in enumerate(names)}
    query_vectors = {name: vectors[len(names) + index] for index, name in enumerate(queries)}
    results = {}
    for key, (raw, candidates) in requests.items():
        try:
            scored = sorted(((_cosine(query_vectors[raw], indexed[item.name]), item)
                             for item in candidates), key=lambda pair: pair[0], reverse=True)
        except ValueError:
            continue
        if not scored:
            continue
        score, winner = scored[0]
        second = scored[1][0] if len(scored) > 1 else -1.0
        if score < settings.subject_embedding_min_similarity or score - second < settings.subject_embedding_min_margin:
            continue
        results[key] = ResolvedSubject(
            raw=raw, code_raw=None, subject_master_id=winner.id,
            code=winner.code, name=winner.name, category=winner.category,
            match_method="embedding",
        )
    return results
