from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    llm_provider: str = "openai"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-5.6-terra"
    subject_embedding_model: str = ""
    subject_embedding_api_key: str = ""
    subject_embedding_base_url: str = ""
    subject_embedding_min_similarity: float = Field(default=0.88, ge=0, le=1)
    subject_embedding_min_margin: float = Field(default=0.08, ge=0, le=1)
    subject_embedding_backend: Literal["local", "remote", "off"] = "local"
    subject_local_embedding_model: str = "BAAI/bge-small-en-v1.5"
    subject_local_embedding_cache_dir: str = ".cache/subject-embeddings"
    subject_local_embedding_min_similarity: float = Field(default=0.62, ge=0, le=1)
    subject_local_embedding_min_margin: float = Field(default=0.06, ge=0, le=1)
    subject_api_base_url: str = ""
    faculty_api_base_url: str = ""
    group_api_base_url: str = ""
    section_api_base_url: str = ""
    parent_class_api_url: str = "https://erp.tint.edu.in/api/public/parent-class-room-list"
    child_class_api_url: str = "https://erp.tint.edu.in/api/public/child-class-room-list"
    master_api_key: str = ""
    master_api_auth_header: str = "Authorization"
    master_api_auth_scheme: str = "Bearer"
    master_cache_ttl_seconds: int = Field(default=300, ge=0)
    max_upload_mb: int = Field(default=15, ge=1, le=100)
    max_pdf_pages: int = Field(default=20, ge=1, le=100)
    max_workbook_cells: int = Field(default=25000, ge=1)
    max_workbook_characters: int = Field(default=200000, ge=1000)
    pdf_render_dpi: int = Field(default=120, ge=72, le=300)
    llm_timeout_seconds: float = Field(default=180, gt=0)
    http_timeout_seconds: float = Field(default=30, gt=0)
    output_dir: str = "output"
