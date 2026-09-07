"""Package local model weights losslessly into Git LFS files below 1 GiB."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = (
    "data/models/BAAI--bge-m3-5617a9f61b02/pytorch_model.bin",
    "data/models/BAAI--bge-reranker-v2-m3-953dc6f6f85a/model.safetensors",
)


def main():
    folder = ROOT / "model-transfer"
    folder.mkdir(exist_ok=True)
    manifest = {"format": 1, "models": []}
    for model_index, relative in enumerate(MODELS, 1):
        whole = hashlib.sha256()
        entry = {"path": relative, "size": 0, "parts": []}
        with (ROOT / relative).open("rb") as source:
            part_index = 0
            while True:
                first = source.read(8 * 1024 * 1024)
                if not first:
                    break
                part_index += 1
                path = folder / f"model-{model_index:02d}-{part_index:03d}.part"
                check = hashlib.sha256()
                count = 0
                with path.open("wb") as output:
                    block = first
                    while block:
                        output.write(block)
                        check.update(block)
                        whole.update(block)
                        count += len(block)
                        if count >= 1024 * 1024 * 1024:
                            break
                        block = source.read(min(8 * 1024 * 1024, 1024 * 1024 * 1024 - count))
                entry["parts"].append({"path": path.relative_to(ROOT).as_posix(), "size": count, "sha256": check.hexdigest()})
                entry["size"] += count
        entry["sha256"] = whole.hexdigest()
        manifest["models"].append(entry)
        print(f"Packaged {relative}: {entry['size']} bytes", flush=True)
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
