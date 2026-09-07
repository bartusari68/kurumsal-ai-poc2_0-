from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from typing import Iterable


def json_dumps(data) -> str:
    return json.dumps(data, ensure_ascii=False)


def json_loads(value: str, default):
    try:
        return json.loads(value)
    except Exception:
        return default


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def canonicalize(value: str) -> str:
    value = value.casefold().strip()
    value = value.translate(str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u"}))
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_")[:255]


def chunk_page_text(text: str, max_chars: int = 1800, overlap: int = 220) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundary = text.rfind(". ", start, end)
            if boundary > start + max_chars // 2:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def demo_embedding(text: str, dim: int = 384) -> list[float]:
    """API anahtarı yokken POC'u ayağa kaldıran basit hashing embedding.

    Gerçek semantic embedding değildir; yalnızca UI/akış geliştirme için fallback'tir.
    """
    tokens = re.findall(r"[\wçğıöşü]+", text.casefold(), flags=re.UNICODE)
    counts = Counter(tokens)
    vec = [0.0] * dim
    for token, count in counts.items():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = -1.0 if digest[4] % 2 else 1.0
        vec[idx] += sign * (1.0 + math.log1p(count))
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def compact_text(value: str, limit: int = 500) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


def extract_json_object(text: str) -> dict:
    text = text.strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, flags=re.S)
    if match:
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}
    return {}
