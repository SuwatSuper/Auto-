# Layer 3 — Infrastructure (scripts/setup_env)
"""Interactive .env bootstrap for one-click launch.

Run before the server starts (called by start.bat / start.sh). It:
  1. Creates .env from .env.example if it does not exist.
  2. If BITKUB_API_KEY is empty, prompts the operator to paste the key + secret
     and writes them into .env (the secret is read without echoing to screen).
  3. Leaves everything untouched if a key is already configured.

No third-party imports — stdlib only, so it runs before/after deps are installed.
"""
from __future__ import annotations

import getpass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_ENV = _ROOT / ".env"
_EXAMPLE = _ROOT / ".env.example"

_KEY_FIELD = "BITKUB_API_KEY"
_SECRET_FIELD = "BITKUB_API_SECRET"


def _read_lines() -> list[str]:
    if _ENV.exists():
        return _ENV.read_text(encoding="utf-8").splitlines()
    if _EXAMPLE.exists():
        return _EXAMPLE.read_text(encoding="utf-8").splitlines()
    # Minimal fallback if neither file exists.
    return [f"{_KEY_FIELD}=", f"{_SECRET_FIELD}="]


def _value_of(lines: list[str], field: str) -> str:
    prefix = field + "="
    for line in lines:
        if line.strip().startswith(prefix):
            return line.split("=", 1)[1].strip()
    return ""


def _set_value(lines: list[str], field: str, value: str) -> list[str]:
    prefix = field + "="
    out: list[str] = []
    found = False
    for line in lines:
        if line.strip().startswith(prefix):
            out.append(f"{field}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{field}={value}")
    return out


def main() -> None:
    lines = _read_lines()

    # Always make sure .env exists on disk.
    if not _ENV.exists():
        _ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("[setup] Created .env")

    existing_key = _value_of(lines, _KEY_FIELD)
    if existing_key:
        print("[setup] Bitkub API key already configured — using the real account.")
        return

    print("")
    print("=================================================================")
    print(" Bitkub API key setup (to see your REAL wallet & portfolio)")
    print(" Create a key at Bitkub > API Management. Read-only is enough.")
    print(" Press ENTER on both to skip and run in paper-only mode.")
    print("=================================================================")
    try:
        key = input(" BITKUB_API_KEY    : ").strip()
        # getpass hides the secret as you type (falls back to visible if no TTY).
        secret = getpass.getpass(" BITKUB_API_SECRET : ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n[setup] Skipped — running paper-only.")
        return

    if not key or not secret:
        print("[setup] No key entered — running paper-only (no real wallet shown).")
        return

    lines = _set_value(lines, _KEY_FIELD, key)
    lines = _set_value(lines, _SECRET_FIELD, secret)
    _ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("[setup] Saved to .env — the real account will be connected on start.")


if __name__ == "__main__":
    main()
