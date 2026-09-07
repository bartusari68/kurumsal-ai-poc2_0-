"""Local, bounded-memory dense retrieval. No PDF text is sent to a model hub."""
from __future__ import annotations

import asyncio
import gc
import hashlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .ai_errors import AIServiceError
from .config import settings

# Explicit revisions: model updates cannot silently change existing vectors.
MODEL_REVISIONS = {
    "BAAI/bge-m3": "5617a9f61b028005a4858fdac845db406aefb181",
    "BAAI/bge-reranker-v2-m3": "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
}
MODEL_WEIGHTS = {
    "BAAI/bge-m3": ("pytorch_model.bin", 2271145830, "b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38"),
    "BAAI/bge-reranker-v2-m3": ("model.safetensors", 2271071852, "d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286"),
}


def model_path(model_name: str) -> Path:
    if model_name not in MODEL_REVISIONS:
        raise AIServiceError("Bu yerel model için doğrulanmış yükleyici tanımlı değil.", code="LOCAL_MODEL_UNSUPPORTED", component="local", status_code=503)
    return settings.local_model_dir / (model_name.replace("/", "--") + "-" + MODEL_REVISIONS[model_name][:12])


def embedding_identity() -> str:
    revision = MODEL_REVISIONS.get(settings.embedding_model, "unsupported")
    return f"local:{settings.embedding_model}@{revision}:cls-norm-v1:{settings.local_max_tokens}"


def download_models() -> None:
    """Explicit setup only; serving requests never starts a large download."""
    os.environ.setdefault("HF_HOME", str(settings.local_model_dir / "hub-cache"))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("HF_XET_CACHE", str(settings.local_model_dir / "hub-cache" / "xet"))
    os.environ.setdefault("HF_XET_NUM_CONCURRENT_RANGE_GETS", "4")
    from huggingface_hub import snapshot_download
    for name in dict.fromkeys([settings.embedding_model, settings.rerank_model]):
        path = model_path(name)
        print(f"Preparing {name} ({MODEL_REVISIONS[name]})", flush=True)
        snapshot_download(repo_id=name, revision=MODEL_REVISIONS[name], local_dir=str(path), token=False,
                          allow_patterns=["config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
                                          "sentencepiece.bpe.model", "pytorch_model.bin" if name == "BAAI/bge-m3" else "model.safetensors"], max_workers=2)
        print(f"Ready on disk: {name}", flush=True)


def verify_downloads() -> None:
    for name in dict.fromkeys([settings.embedding_model, settings.rerank_model]):
        filename, expected_size, expected_hash = MODEL_WEIGHTS[name]
        path = model_path(name) / filename
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(block)
        if path.stat().st_size != expected_size or digest.hexdigest() != expected_hash:
            raise RuntimeError(f"Model checksum verification failed: {name}")
        print(f"SHA-256 verified: {name}", flush=True)


class LocalModelRuntime:
    def __init__(self):
        # One model and one inference at a time, including requests from other tabs.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="local-rag")
        self._model = None
        self._tokenizer = None
        self._loaded = None
        self._device = "cpu"
        self._state = {"status": "idle", "component": None, "device": "cpu"}

    @property
    def status(self) -> dict:
        return dict(self._state)

    def _release(self):
        self._model = self._tokenizer = self._loaded = None
        gc.collect()

    def close(self):
        self._executor.shutdown(wait=True, cancel_futures=True)
        self._release()

    def _load(self, component: str):
        name = settings.embedding_model if component == "embedding" else settings.rerank_model
        if self._loaded == (component, name):
            return self._tokenizer, self._model
        path = model_path(name)
        if not (path / "config.json").is_file() or not any((path / name).is_file() for name in ("model.safetensors", "pytorch_model.bin")):
            raise AIServiceError("Yerel PDF modelleri henüz hazırlanmadı. kurulum.cmd ile model kurulumunu tamamlayın.",
                                 code="LOCAL_MODEL_NOT_READY", component=component, status_code=503)
        self._release()
        self._state.update(status="loading", component=component)
        import torch
        from transformers import AutoModel, AutoModelForSequenceClassification, AutoTokenizer
        torch.set_num_threads(settings.local_threads)
        self._device = settings.local_device
        if self._device == "auto":
            self._device = "cuda" if torch.cuda.is_available() and torch.cuda.mem_get_info()[0] > 2.5 * 1024**3 else "cpu"
        if self._device == "cuda" and not torch.cuda.is_available():
            raise AIServiceError("CUDA çalıştırma bileşeni bulunmuyor. LOCAL_DEVICE=cpu kullanın.", code="LOCAL_DEVICE_UNAVAILABLE", component=component, status_code=503)
        factory = AutoModel if component == "embedding" else AutoModelForSequenceClassification
        tokenizer = AutoTokenizer.from_pretrained(str(path), local_files_only=True, trust_remote_code=False)
        model = factory.from_pretrained(str(path), local_files_only=True, trust_remote_code=False,
                                        dtype=torch.float16 if self._device == "cuda" else torch.float32,
                                        weights_only=True, low_cpu_mem_usage=True)
        model.to(self._device).eval()
        self._model, self._tokenizer, self._loaded = model, tokenizer, (component, name)
        self._state.update(status="ready", component=component, device=self._device)
        return tokenizer, model

    def _run(self, component, operation, *args):
        try:
            return operation(*args)
        except AIServiceError:
            self._state.update(status="error", component=component)
            raise
        except Exception as exc:
            self._release()
            self._state.update(status="error", component=component)
            logging.getLogger(__name__).warning("Local inference failed: component=%s type=%s", component, type(exc).__name__)
            raise AIServiceError("Yerel PDF modeli çalıştırılamadı. Kurulumun tamamlandığını ve yeterli boş bellek bulunduğunu kontrol edin.",
                                 code="LOCAL_INFERENCE_FAILED", component=component, status_code=503) from exc

    def _embed(self, texts):
        import torch
        tokenizer, model = self._load("embedding")
        vectors = []
        with torch.inference_mode():
            for start in range(0, len(texts), settings.local_batch_size):
                inputs = tokenizer(texts[start:start + settings.local_batch_size], padding=True, truncation=True,
                                   max_length=settings.local_max_tokens, return_tensors="pt").to(self._device)
                # BGE-M3 dense representation: normalized CLS; no query/passage prefix.
                outputs = model(**inputs).last_hidden_state[:, 0]
                vectors.extend(torch.nn.functional.normalize(outputs.float(), p=2, dim=1).cpu().tolist())
        return vectors

    def _rerank(self, query, documents, top_n):
        import torch
        tokenizer, model = self._load("rerank")
        scores = []
        with torch.inference_mode():
            for start in range(0, len(documents), settings.local_batch_size):
                pairs = [[query, doc] for doc in documents[start:start + settings.local_batch_size]]
                inputs = tokenizer(pairs, padding=True, truncation=True, max_length=settings.local_max_tokens, return_tensors="pt").to(self._device)
                scores.extend(model(**inputs).logits.view(-1).float().sigmoid().cpu().tolist())
        return sorted([{"index": i, "relevance_score": score} for i, score in enumerate(scores)],
                      key=lambda item: item["relevance_score"], reverse=True)[:top_n]

    async def embed(self, texts):
        if not texts:
            return []
        return await asyncio.get_running_loop().run_in_executor(self._executor, self._run, "embedding", self._embed, texts)

    async def rerank(self, query, documents, top_n):
        if not documents or top_n <= 0:
            return []
        return await asyncio.get_running_loop().run_in_executor(self._executor, self._run, "rerank", self._rerank, query, documents, top_n)


local_models = LocalModelRuntime()
