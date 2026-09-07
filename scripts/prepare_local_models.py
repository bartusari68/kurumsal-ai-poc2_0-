"""Download pinned local model weights and optionally verify real inference."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.local_models import download_models, local_models, verify_downloads


async def verify():
    vectors = await local_models.embed(["Excel pivot tablo eğitimi", "Python otomasyon eğitimi"])
    scores = await local_models.rerank("Excel pivot tablo", ["Excel pivot tablo eğitimi", "Python otomasyon eğitimi"], 2)
    assert len(vectors) == 2 and len(vectors[0]) == 1024
    assert scores[0]["index"] == 0
    print(json.dumps({"verified": True, "dimension": len(vectors[0]), "ranking": scores, "runtime": local_models.status}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    options = parser.parse_args()
    download_models()
    if options.verify:
        verify_downloads()
        try:
            asyncio.run(verify())
        finally:
            local_models.close()
