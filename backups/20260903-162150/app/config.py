from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "").strip()
    openrouter_base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    llm_model: str = os.getenv("LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "nvidia/nemotron-3-embed-1b:free")
    rerank_model: str = os.getenv("RERANK_MODEL", "nvidia/llama-nemotron-rerank-vl-1b-v2:free")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
    pdf_dir: Path = Path(os.getenv("PDF_DIR", "./data/pdfs"))
    top_k_retrieve: int = int(os.getenv("TOP_K_RETRIEVE", "16"))
    top_k_rerank: int = int(os.getenv("TOP_K_RERANK", "6"))

    @property
    def ai_mode(self) -> str:
        return "openrouter" if self.openrouter_api_key else "demo"


settings = Settings()
settings.pdf_dir.mkdir(parents=True, exist_ok=True)
