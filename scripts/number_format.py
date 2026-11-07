"""Un nombre à la française — espace des milliers, virgule décimale."""
from __future__ import annotations


def fr_number(value: float, digits: int = 2, *, signed: bool = False,
              grouped: bool = True) -> str:
    """`value` à `digits` décimales ; `signed` force le signe, `grouped` sépare"""
    spec = f"{'+' if signed else ''}{',' if grouped else ''}.{digits}f"
    return format(value, spec).replace(",", " ").replace(".", ",")
