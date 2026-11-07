#!/usr/bin/env python3
"""LA LOI D'ÉCRITURE DES JSON — une seule forme, pour que le diff dise la vérité."""
from __future__ import annotations

import json
from pathlib import Path

import atomic_file
import data_root
import reference_layout

SKILL = Path(__file__).resolve().parent.parent
REFS = SKILL / "references"


PRODUCT_REFS = REFS


INDENT = 2
END_OF_LINE = "\n"





A_LA_MAIN = {
    "baskets.json": (
        "manifeste des paniers — mis en forme à la main, UN MEMBRE PAR LIGNE "
        "(conid, symbole, place, nom). C'est cette forme qui le rend relisable : "
        "sous la loi, chaque membre s'étalerait sur six lignes et le fichier "
        "passerait de ~800 à ~4000 lignes. Aucun script ne l'écrit (vérifié le "
        "2026-07-29) — il n'y a donc pas deux conventions qui se croisent, "
        "c'est-à-dire pas le défaut que la loi corrige."
    ),
}


def dans_le_perimetre(chemin: Path) -> bool:
    """Le fichier est-il soumis à la loi ? `references/*.json`, hors exception."""
    chemin = Path(chemin).resolve()
    if chemin.suffix != ".json" or chemin.parent != Path(REFS).resolve():
        return False
    return chemin.name not in A_LA_MAIN








INSTRUMENTS_DIRNAME = "instruments"


def is_instrument_sheet(path) -> bool:
    """Le fichier est-il une fiche instrument ? (`references/instruments/*.json`)"""
    path = Path(path).resolve()



    folders = {(REFS / INSTRUMENTS_DIRNAME).resolve(),
               (data_root.book_refs() / INSTRUMENTS_DIRNAME).resolve()}
    return path.suffix == ".json" and path.parent in folders


def normalize_sheet_category(obj):
    """Valide `identity.category` et traduit un alias SUR UNE COPIE."""
    if not isinstance(obj, dict):
        return obj
    identity = obj.get("identity")
    if not isinstance(identity, dict) or "category" not in identity:
        return obj
    from instrument_categories import normalize_category
    try:
        canonical = normalize_category(identity["category"])
    except ValueError as error:
        raise ValueError(
            f"catégorie d'instrument refusée : {identity['category']!r}\n"
            f"  {error}\n"
            f"  le fichier sur disque n'a pas été touché."
        ) from error
    if canonical == identity["category"]:
        return obj
    copy = dict(obj)
    copy["identity"] = {**identity, "category": canonical}
    return copy





FACT_TEXTS = ("detail", "cash", "risk")


def check_fact_texts(obj) -> None:
    """Refuse un texte de `facts` qui n'est ni une chaîne ni `None`."""
    facts = obj.get("facts") if isinstance(obj, dict) else None
    if not isinstance(facts, dict):
        return
    for key in FACT_TEXTS:
        if facts.get(key) is not None and not isinstance(facts[key], str):
            raise ValueError(
                f"facts.{key} doit être du texte, pas {type(facts[key]).__name__} : "
                f"le dashboard refuserait la fiche (erreur 500)\n"
                f"  le fichier sur disque n'a pas été touché."
            )


def rendre(obj) -> str:
    """Le texte EXACT que la loi impose pour cet objet. La seule source de forme."""
    return json.dumps(obj, ensure_ascii=False, indent=INDENT) + END_OF_LINE


def charger(chemin) -> object:
    """Lire un JSON. Rien de spécial — il existe pour que lecture et écriture"""
    return json.loads(Path(chemin).read_text(encoding="utf-8"))


def misplaced_book_write(chemin) -> str | None:
    """Le motif du refus si `chemin` recrée le livre dans le dépôt produit."""
    if not data_root.book_is_external():
        return None
    try:
        relative = Path(chemin).resolve().relative_to(PRODUCT_REFS.resolve())
    except ValueError:
        return None
    if not relative.parts or reference_layout.kind_of(relative.parts[0]) != reference_layout.BOOK:
        return None
    return (f"écriture refusée : {Path('references', *relative.parts)} appartient au livre, qui vit "
            f"sous {data_root.book_refs()} — passer par data_root.book_refs()")


def write(chemin, obj) -> None:
    """Écrire un JSON SOUS LA LOI, de façon atomique."""
    chemin = Path(chemin)
    misplaced = misplaced_book_write(chemin)
    if misplaced:
        raise ValueError(misplaced)
    if chemin.name in A_LA_MAIN and chemin.resolve().parent == REFS:
        raise ValueError(
            f"{chemin.name} est déclaré À LA MAIN dans jsonio.A_LA_MAIN — "
            f"l'écrire sous la loi détruirait sa mise en forme.\n"
            f"  raison : {A_LA_MAIN[chemin.name]}\n"
            f"  si un script doit désormais le produire, retire l'exception "
            f"EXPRESSÉMENT et assume le reformatage."
        )
    if is_instrument_sheet(chemin):
        obj = normalize_sheet_category(obj)
        check_fact_texts(obj)


        from trial_registry import check_sheet
        check_sheet(obj)


        import catalyst_kinds
        catalyst_kinds.check_sheet(obj)


        import catalyst_check
        catalyst_check.check_sheet(obj)


    atomic_file.write_text(chemin, rendre(obj))


def conforme(chemin) -> bool:
    """Le fichier sur disque est-il DÉJÀ dans la forme de la loi, octet à octet ?"""
    chemin = Path(chemin)
    return chemin.read_text(encoding="utf-8") == rendre(charger(chemin))


if __name__ == "__main__":
    print(__doc__)
    print(f"  loi : indent={INDENT}, ensure_ascii=False, saut de ligne final,")
    print("        ordre des clés préservé (jamais de tri implicite)")
    print(f"  périmètre : references/*.json — {len(A_LA_MAIN)} exception(s) déclarée(s)")
    for name, why in A_LA_MAIN.items():
        print(f"    · {name} — {why[:70]}…")
