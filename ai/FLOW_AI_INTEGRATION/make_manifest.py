"""Write MANIFEST.json (sha256 + size of every file in this package, excluding venv/caches/.env)."""
import hashlib, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
SKIP = {".venv", "__pycache__", ".env", "MANIFEST.json", "pip.log", "live"}


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main(check=False):
    files = sorted(p for p in HERE.rglob("*") if p.is_file() and not (set(p.relative_to(HERE).parts) & SKIP))
    m = {p.relative_to(HERE).as_posix(): {"sha256": sha(p), "bytes": p.stat().st_size} for p in files}
    if check:
        old = json.loads((HERE / "MANIFEST.json").read_text(encoding="utf-8"))["files"]
        bad = [k for k in old if k not in m or m[k]["sha256"] != old[k]["sha256"]]
        print("MANIFEST", "OK" if not bad else f"MISMATCH {bad}"); return 1 if bad else 0
    (HERE / "MANIFEST.json").write_text(json.dumps({"package": "FLOW_AI_INTEGRATION", "model_version": "integration_demo_01",
        "model_role": "integration_demo_not_final", "total_bytes": sum(v["bytes"] for v in m.values()), "files": m}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(len(m), "files", round(sum(v["bytes"] for v in m.values()) / 2**20, 2), "MB"); return 0


if __name__ == "__main__":
    raise SystemExit(main("--check" in sys.argv))
