# Layer 3 — Infrastructure (scripts/setup_env)
"""Non-interactive .env bootstrap for one-click launch.

Run before the server starts (called by start.bat / start.sh / start.ps1). It:
  1. Creates .env from .env.example if it does not exist.
  2. Ensures a private DASHBOARD_API_KEY exists (auto-generated) so the
     dashboard's control buttons work on localhost with ZERO setup.

It does NOT prompt for anything. The Bitkub API key/secret is entered in exactly
ONE place — the dashboard "Connect" form — so startup never blocks on a prompt
and there is only a single point to connect the account.

No third-party imports — stdlib only, so it runs before/after deps are installed.
"""
from __future__ import annotations

import secrets
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_ENV = _ROOT / ".env"
_EXAMPLE = _ROOT / ".env.example"

_KEY_FIELD = "BITKUB_API_KEY"
_SECRET_FIELD = "BITKUB_API_SECRET"

# Control-plane key. Auto-generated once so the operator never types it: the
# server injects it into the dashboard page, which sends it back automatically.
_DASH_KEY_FIELD = "DASHBOARD_API_KEY"
_DASH_PLACEHOLDER = "put-your-secret-key-here"


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


def _ensure_dashboard_key(lines: list[str]) -> tuple[list[str], bool]:
    """Guarantee DASHBOARD_API_KEY holds a real secret.

    Generates a strong random key when the field is empty or still the shipped
    placeholder, so the operator never has to type a control-plane key — the
    dashboard injects it automatically on every load. An existing real key is
    left untouched. Returns (lines, generated?).
    """
    current = _value_of(lines, _DASH_KEY_FIELD)
    if current and current != _DASH_PLACEHOLDER:
        return lines, False
    return _set_value(lines, _DASH_KEY_FIELD, secrets.token_urlsafe(24)), True


def main() -> None:
    """Non-interactive: ensure .env exists with a private control key. The Bitkub
    key/secret is entered ONCE on the dashboard form — never here — so startup
    never blocks on a prompt and there is a single point to connect."""
    lines = _read_lines()
    lines, generated_dash = _ensure_dashboard_key(lines)

    if not _ENV.exists():
        _ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("[setup] Created .env")
    elif generated_dash:
        _ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if _value_of(lines, _KEY_FIELD):
        print("[setup] Ready. Bitkub account already connected.")
    else:
        print("[setup] Ready. Connect your Bitkub account ONCE on the dashboard "
              "(the 'Connect' form) — no key needed here.")


if __name__ == "__main__":
    main()
