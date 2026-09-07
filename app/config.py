from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    groq_api_key: str = field(default=os.getenv("GROQ_API_KEY", "").strip(), repr=False)
    groq_base_url: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    llm_provider: str = os.getenv("LLM_PROVIDER", "").strip().lower()
    openrouter_api_key: str = field(default=os.getenv("OPENROUTER_API_KEY", "").strip(), repr=False)
    openrouter_base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    llm_model: str = (
        os.getenv("LLM_MODEL", "").strip()
        or os.getenv("PRIMARY_LLM_MODEL", "").strip()
        or "nvidia/nemotron-3-super-120b-a12b:free"
    )
    fallback_llm_model: str = os.getenv("FALLBACK_LLM_MODEL", "").strip()
    chat_model: str = os.getenv("CHAT_MODEL", "").strip()
    primary_reasoning_effort: str = os.getenv("PRIMARY_REASONING_EFFORT", "medium").strip()
    fallback_reasoning_effort: str = os.getenv("FALLBACK_REASONING_EFFORT", "high").strip()
    chat_reasoning_effort: str = os.getenv("CHAT_REASONING_EFFORT", "none").strip()
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    chat_temperature: float = float(os.getenv("CHAT_TEMPERATURE", "0.2"))
    max_output_tokens: int = int(os.getenv("MAX_OUTPUT_TOKENS", "4096"))
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "openrouter").strip().lower()
    rerank_provider: str = os.getenv("RERANK_PROVIDER", "openrouter").strip().lower()
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "nvidia/nemotron-3-embed-1b:free")
    rerank_model: str = os.getenv("RERANK_MODEL", "nvidia/llama-nemotron-rerank-vl-1b-v2:free")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
    pdf_dir: Path = Path(os.getenv("PDF_DIR", "./data/pdfs"))
    top_k_retrieve: int = int(os.getenv("TOP_K_RETRIEVE", "16"))
    top_k_rerank: int = int(os.getenv("TOP_K_RERANK", "6"))
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "1800"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "220"))
    local_model_dir: Path = Path(os.getenv("LOCAL_MODEL_DIR", "./data/models"))
    local_device: str = os.getenv("LOCAL_DEVICE", "cpu")
    local_batch_size: int = int(os.getenv("LOCAL_BATCH_SIZE", "2"))
    local_max_tokens: int = int(os.getenv("LOCAL_MAX_TOKENS", "1024"))
    local_threads: int = int(os.getenv("LOCAL_THREADS", "4"))

    def __post_init__(self):
        provider = self.llm_provider or ("groq" if self.groq_api_key else "openrouter")
        if provider not in ("groq", "openrouter"):
            raise ValueError("LLM_PROVIDER groq veya openrouter olmalı.")
        object.__setattr__(self, "llm_provider", provider)
        if self.embedding_provider not in ("local", "openrouter") or self.rerank_provider not in ("local", "openrouter"):
            raise ValueError("Arama sağlayıcısı local veya openrouter olmalı.")
        if not 0 <= self.chunk_overlap < self.chunk_size or self.chunk_size < 100:
            raise ValueError("CHUNK_SIZE en az 100; CHUNK_OVERLAP daha küçük ve negatif olmayan bir değer olmalı.")
        if self.local_batch_size < 1 or self.local_threads < 1 or self.local_max_tokens < 32:
            raise ValueError("Yerel model çalışma sınırları geçersiz.")
        # Relative paths belong to this application, not the launch directory.
        pdf_dir = self.pdf_dir if self.pdf_dir.is_absolute() else PROJECT_ROOT / self.pdf_dir
        object.__setattr__(self, "pdf_dir", pdf_dir.resolve())
        model_dir = self.local_model_dir if self.local_model_dir.is_absolute() else PROJECT_ROOT / self.local_model_dir
        object.__setattr__(self, "local_model_dir", model_dir.resolve())
        from sqlalchemy.engine import make_url
        url = make_url(self.database_url)
        if url.drivername.startswith("sqlite") and url.database not in (None, "", ":memory:"):
            database = Path(url.database)
            if not database.is_absolute():
                url = url.set(database=(PROJECT_ROOT / database).resolve().as_posix())
                object.__setattr__(self, "database_url", str(url))

    @property
    def ai_mode(self) -> str:
        return self.llm_provider if self.api_key else "off"

    @property
    def api_key(self) -> str:
        return self.groq_api_key if self.llm_provider == "groq" else self.openrouter_api_key

    @property
    def api_base_url(self) -> str:
        return self.groq_base_url if self.llm_provider == "groq" else self.openrouter_base_url


settings = Settings()
settings.pdf_dir.mkdir(parents=True, exist_ok=True)
