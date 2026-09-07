from __future__ import annotations

import re
from typing import Any

import httpx

from .config import settings
from .utils import canonicalize, demo_embedding, extract_json_object


class AIClient:
    def __init__(self) -> None:
        self.api_key = settings.openrouter_api_key
        self.base_url = settings.openrouter_base_url

    @property
    def provider_name(self) -> str:
        return settings.embedding_model if self.api_key else "demo-hash-v1"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": "Kurumsal AI POC",
        }

    async def embed(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]:
        if not self.api_key:
            return [demo_embedding(text) for text in texts]

        # NVIDIA model kartında retrieval için query:/passage: prefix'i öneriliyor.
        prefix = "query: " if is_query else "passage: "
        payload = {
            "model": settings.embedding_model,
            "input": [prefix + t for t in texts],
            "encoding_format": "float",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{self.base_url}/embeddings", headers=self._headers(), json=payload)
            response.raise_for_status()
            data = response.json()["data"]
        data = sorted(data, key=lambda item: item["index"])
        return [item["embedding"] for item in data]

    async def rerank(self, query: str, documents: list[str], top_n: int) -> list[dict[str, Any]]:
        if not documents:
            return []
        if not self.api_key:
            return [
                {"index": i, "relevance_score": 1.0 - (i / max(1, len(documents))), "document": {"text": d}}
                for i, d in enumerate(documents[:top_n])
            ]

        payload = {
            "model": settings.rerank_model,
            "query": query,
            "documents": documents,
            "top_n": min(top_n, len(documents)),
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{self.base_url}/rerank", headers=self._headers(), json=payload)
            response.raise_for_status()
            return response.json().get("results", [])

    async def chat_json(self, system: str, user: str) -> dict[str, Any]:
        if not self.api_key:
            return {}
        payload = {
            "model": settings.llm_model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(f"{self.base_url}/chat/completions", headers=self._headers(), json=payload)
            response.raise_for_status()
            text = response.json()["choices"][0]["message"]["content"]
        return extract_json_object(text)

    async def chat_text(self, system: str, user: str) -> str:
        if not self.api_key:
            return "DEMO modunda gerçek LLM cevabı kapalı. OPENROUTER_API_KEY eklediğinizde bu alan Nemotron ile cevap üretir."
        payload = {
            "model": settings.llm_model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(f"{self.base_url}/chat/completions", headers=self._headers(), json=payload)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()

    async def classify_request(self, text: str) -> dict[str, Any]:
        result = await self.chat_json(
            """Sen şirket içi talep sınıflandırma motorusun. Yalnızca geçerli JSON üret.
Türkçe talepleri kısa ve tutarlı bir kurumsal forma normalize et.
Alanlar: category, topic, intent, canonical_intent, keywords.
canonical_intent kısa ve tekrar kullanılabilir olmalı; örn. excel_yetkinlik_gelistirme.""",
            text,
        )
        if result:
            result["canonical_intent"] = canonicalize(str(result.get("canonical_intent") or result.get("topic") or text))
            return result

        lower = text.casefold()
        topic = "Microsoft Excel" if "excel" in lower else "Genel Eğitim"
        if any(k in lower for k in ["eğitim", "egitim", "öğren", "ogren", "geliştir", "gelistir", "yetkin"]):
            category = "Eğitim Talebi"
            intent = "Yetkinlik Geliştirme"
        else:
            category = "Genel Talep"
            intent = "Bilgi / Destek"
        canonical = canonicalize(f"{topic}_{intent}")
        return {
            "category": category,
            "topic": topic,
            "intent": intent,
            "canonical_intent": canonical,
            "keywords": re.findall(r"[\wçğıöşü]+", lower)[:8],
        }

    async def coverage_analysis(self, request_text: str, classification: dict, evidence: list[dict]) -> dict[str, Any]:
        context = "\n".join(
            f"- {e['course_code']} | {e['course_name']} | sayfa {e['page_number']} | skor={e['score']:.3f} | {e['content']}"
            for e in evidence
        )
        result = await self.chat_json(
            """Sen ders içeriği kapsama analisti olarak çalışıyorsun. Sana kullanıcı talebi ve yalnızca retrieval ile bulunan kanıtlar verilecek.
Kanıt olmayan şeyi uydurma. Yalnızca JSON üret.
Şema: {"coverage":"VAR|KISMEN_VAR|YOK","confidence":0.0,"reason":"...","missing_topics":["..."],"matched_course_codes":["..."]}.
VAR: ihtiyaç güçlü biçimde karşılanıyor. KISMEN_VAR: ihtiyacın bir bölümü var ama önemli eksikler var. YOK: yeterli kanıt yok.""",
            f"TALEP:\n{request_text}\n\nSINIFLANDIRMA:\n{classification}\n\nKANITLAR:\n{context or 'Kanıt bulunamadı.'}",
        )
        if result:
            coverage = str(result.get("coverage", "BELIRSIZ")).upper().replace(" ", "_")
            if coverage not in {"VAR", "KISMEN_VAR", "YOK"}:
                coverage = "BELIRSIZ"
            result["coverage"] = coverage
            try:
                result["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
            except Exception:
                result["confidence"] = 0.0
            return result

        if not evidence:
            return {"coverage": "YOK", "confidence": 0.7, "reason": "İlgili ders içeriği bulunamadı.", "missing_topics": [], "matched_course_codes": []}
        best = evidence[0]["score"]
        if best >= 0.72:
            coverage = "VAR"
        elif best >= 0.42:
            coverage = "KISMEN_VAR"
        else:
            coverage = "YOK"
        return {
            "coverage": coverage,
            "confidence": round(max(0.45, min(0.95, best)), 2),
            "reason": "DEMO modunda sonuç retrieval skorlarına göre üretilmiştir.",
            "missing_topics": [],
            "matched_course_codes": [evidence[0]["course_code"]] if evidence else [],
        }


ai_client = AIClient()
