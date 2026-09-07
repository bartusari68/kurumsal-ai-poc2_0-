"""Restore losslessly split model weights after git lfs pull (stdlib only)."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def within_root(relative):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Manifest path escapes project directory")
    return path


def main():
    manifest = json.loads((ROOT / "model-transfer/manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["models"]:
        target = within_root(entry["path"])
        if target.exists() and digest(target) == entry["sha256"]:
            print(f"Verified: {entry['path']}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".restoring")
        whole = hashlib.sha256()
        size = 0
        created = False
        try:
            with temporary.open("xb") as output:
                created = True
                for part in entry["parts"]:
                    piece = within_root(part["path"])
                    check = hashlib.sha256()
                    count = 0
                    with piece.open("rb") as source:
                        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
                            check.update(block)
                            whole.update(block)
                            output.write(block)
                            count += len(block)
                    if count != part["size"] or check.hexdigest() != part["sha256"]:
                        raise ValueError(f"Missing or damaged LFS content: {part['path']}. Run git lfs pull.")
                    size += count
            if size != entry["size"] or whole.hexdigest() != entry["sha256"]:
                raise ValueError(f"Model integrity check failed: {entry['path']}")
            os.replace(temporary, target)
        except Exception:
            if created:
                temporary.unlink(missing_ok=True)
            raise
        print(f"Restored and verified: {entry['path']}")


if __name__ == "__main__":
    main()
