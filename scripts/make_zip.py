# scripts/make_zip.py — package the project, excluding secrets and build artifacts
"""Usage: python scripts/make_zip.py <suffix>
Creates kingdom_prime_<suffix>.zip at the repo root.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

_EXCLUDE_NAMES = {".env", ".git", ".venv", "venv", "__pycache__",
                  ".pytest_cache", ".mypy_cache", ".ruff_cache", ".coverage",
                  "data", "logs", "wheels"}

_EXCLUDE_SUFFIXES = {".zip"}


def _should_exclude(rel: Path) -> bool:
    parts = rel.parts
    if any(p in _EXCLUDE_NAMES for p in parts):
        return True
    if rel.suffix in _EXCLUDE_SUFFIXES:
        return True
    return False


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/make_zip.py <suffix>")
        sys.exit(1)

    suffix = sys.argv[1]
    repo_root = Path(__file__).parent.parent.resolve()
    zip_name = f"kingdom_prime_{suffix}.zip"
    zip_path = repo_root / zip_name

    count = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(repo_root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(repo_root)
            if _should_exclude(rel):
                continue
            # Hard security requirement: never archive .env
            assert not str(rel).endswith(".env"), f"Refusing to archive secret file: {rel}"
            zf.write(path, rel)
            count += 1

    print(f"Created: {zip_path}")
    print(f"Files added: {count}")


if __name__ == "__main__":
    main()
