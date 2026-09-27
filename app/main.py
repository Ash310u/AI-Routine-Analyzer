from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from openai import APIConnectionError, APIError, APITimeoutError

from app.clients.master_api import MasterAPI, MasterDataError
from app.config import Settings
from app.ingestion.document import DocumentError
from app.llm.extractor import ExtractionError, ModelServiceError
from app.schemas.routine import StandardizedDocument, StandardizedWorkbook
from app.services.routine_processor import process_routine
from app.services.output_store import save_routine


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.master_api = MasterAPI(Settings())
    try:
        yield
    finally:
        await app.state.master_api.aclose()


app = FastAPI(title="Routine Standardizer", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/routines/standardize", response_model=StandardizedWorkbook | StandardizedDocument)
async def standardize(
    file: UploadFile = File(...), college_id: int = Query(..., ge=1),
) -> StandardizedWorkbook | StandardizedDocument:
    settings = Settings()
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail="File exceeds upload limit")
    try:
        routine = await process_routine(data, settings, app.state.master_api, college_id)
        save_routine(routine, file.filename, settings)
        return routine
    except DocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ModelServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except MasterDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except APITimeoutError as exc:
        raise HTTPException(status_code=504, detail=f"OpenAI request timed out after {settings.llm_timeout_seconds:g} seconds") from exc
    except APIConnectionError as exc:
        raise HTTPException(status_code=502, detail="Could not connect to the OpenAI API; check DNS, network access, and LLM_BASE_URL") from exc
    except APIError as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI API error: {exc.message}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Upstream service request failed") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Routine processed but could not be saved to the output directory") from exc
