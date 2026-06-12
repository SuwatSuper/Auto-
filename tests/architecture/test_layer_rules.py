# Layer 2 — Orchestration (tests/architecture/test_layer_rules)
"""Machine-enforced layer purity tests using AST analysis."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).parent.parent.parent / "src"
_STDLIB = sys.stdlib_module_names


def _collect_imports(path: Path) -> set[str]:
    """Return module-level imported roots for a .py file (not local/function-scope imports)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    roots: set[str] = set()
    # Only walk module-level statements (tree.body), not nested function bodies.
    # Local imports inside functions are allowed for circular-import avoidance.
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def _py_files(under: Path) -> list[Path]:
    return sorted(under.rglob("*.py"))


# --- Layer 1: domain must import only stdlib + pydantic + domain ---

def test_domain_no_structlog() -> None:
    """Layer 1: domain must not import structlog."""
    for path in _py_files(_SRC / "domain"):
        imports = _collect_imports(path)
        assert "structlog" not in imports, (
            f"{path.relative_to(_SRC)}: Layer 1 must not import structlog"
        )


def test_domain_no_orjson() -> None:
    """Layer 1: domain must not import orjson."""
    for path in _py_files(_SRC / "domain"):
        imports = _collect_imports(path)
        assert "orjson" not in imports, (
            f"{path.relative_to(_SRC)}: Layer 1 must not import orjson"
        )


def test_domain_no_infrastructure() -> None:
    """Layer 1: domain must not import infrastructure."""
    for path in _py_files(_SRC / "domain"):
        imports = _collect_imports(path)
        assert "infrastructure" not in imports, (
            f"{path.relative_to(_SRC)}: Layer 1 must not import infrastructure"
        )


def test_domain_no_asyncio_side_effects() -> None:
    """Layer 1: domain must not import asyncio (determinism requirement)."""
    for path in _py_files(_SRC / "domain"):
        imports = _collect_imports(path)
        assert "asyncio" not in imports, (
            f"{path.relative_to(_SRC)}: Layer 1 must not import asyncio"
        )


@pytest.mark.parametrize("forbidden", ["time", "random", "os"])
def test_domain_no_forbidden_modules(forbidden: str) -> None:
    """Layer 1: domain must not import time, random, or os (non-determinism)."""
    for path in _py_files(_SRC / "domain"):
        imports = _collect_imports(path)
        assert forbidden not in imports, (
            f"{path.relative_to(_SRC)}: Layer 1 must not import '{forbidden}'"
        )


def test_domain_only_allowed_roots() -> None:
    """Layer 1: domain imports must come from stdlib, pydantic, or domain."""
    allowed_roots = _STDLIB | {"pydantic", "domain"}
    for path in _py_files(_SRC / "domain"):
        imports = _collect_imports(path)
        bad = imports - allowed_roots - {"__future__"}
        assert not bad, (
            f"{path.relative_to(_SRC)}: Layer 1 forbidden imports: {bad}"
        )


# --- Layer 2: orchestration must import only stdlib + domain + orchestration + structlog ---

def test_orchestration_no_infrastructure() -> None:
    """Layer 2: orchestration must not import infrastructure directly."""
    for path in _py_files(_SRC / "orchestration"):
        imports = _collect_imports(path)
        assert "infrastructure" not in imports, (
            f"{path.relative_to(_SRC)}: Layer 2 must not import infrastructure"
        )


def test_orchestration_allowed_roots() -> None:
    """Layer 2: orchestration imports must stay within allowed set."""
    allowed_roots = _STDLIB | {"domain", "orchestration", "structlog", "orjson", "pydantic"}
    for path in _py_files(_SRC / "orchestration"):
        imports = _collect_imports(path)
        bad = imports - allowed_roots - {"__future__"}
        assert not bad, (
            f"{path.relative_to(_SRC)}: Layer 2 forbidden imports: {bad}"
        )


# --- bootstrap.py and infrastructure are allowed to import everything ---

def test_bootstrap_imports_infrastructure() -> None:
    """bootstrap.py is the composition root; it SHOULD import infrastructure."""
    imports = _collect_imports(_SRC / "bootstrap.py")
    assert "infrastructure" in imports, "bootstrap.py must import infrastructure adapters"


# --- Float ban in financial domain modules ---

def _check_no_float(path: Path) -> list[str]:
    """Return violations: float literals or annotations in the given file."""
    if not path.exists():
        return []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    violations: list[str] = []

    class _FloatVisitor(ast.NodeVisitor):
        def visit_Constant(self, node: ast.Constant) -> None:
            if isinstance(node.value, float):
                violations.append(
                    f"float literal at line {node.lineno}: {node.value}"
                )
            self.generic_visit(node)

        def visit_Name(self, node: ast.Name) -> None:
            if node.id == "float":
                violations.append(f"'float' annotation/reference at line {node.lineno}")
            self.generic_visit(node)

    _FloatVisitor().visit(tree)
    return violations


@pytest.mark.parametrize(
    "subpath",
    [
        "domain/portfolio",
        "domain/risk",
        "domain/backtest",
    ],
)
def test_no_float_in_financial_domain(subpath: str) -> None:
    """Layer 1 financial modules must not use float literals or annotations."""
    folder = _SRC / subpath
    if not folder.exists():
        pytest.skip(f"{subpath} does not exist yet (added in P2)")
        return
    for path in _py_files(folder):
        violations = _check_no_float(path)
        assert not violations, (
            f"{path.relative_to(_SRC)}: float banned in financial domain:\n"
            + "\n".join(violations)
        )
