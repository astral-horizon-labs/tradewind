"""Chaque entrée de `references/` : méthode livrée avec le skill, ou livre personnel."""
from __future__ import annotations

import argparse
import fnmatch
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
REFERENCES = ROOT / "references"

METHOD, BOOK, MIXED = "method", "book", "mixed"
KIND_LABELS = {METHOD: "méthode livrée", BOOK: "livre personnel", MIXED: "à scinder"}


LAYOUT: dict[str, tuple[str, str]] = {

    "instruments": (BOOK, "les fiches : identité, faits, et SES décisions et niveaux"),
    "research": (BOOK, "ses dossiers transversaux et études datées"),
    "document-inventory.md": (BOOK, "inventaire GÉNÉRÉ de ses fiches et dossiers"),
    "open-topics.md": (BOOK, "ses topics ouverts, mesures datées"),
    "decisions.jsonl": (BOOK, "historique de son jugement, append-only"),
    "plan-events.jsonl": (BOOK, "journal des événements de ses plans"),
    "exit-reviews.jsonl": (BOOK, "ses revues de sortie"),
    "thesis-reviews.jsonl": (BOOK, "ses revues de thèse"),
    "forecasts.jsonl": (BOOK, "ses prévisions et leur résolution"),
    "finding-clearances.jsonl": (BOOK, "ses levées de constats"),
    "blind-readings.jsonl": (BOOK, "ses lectures à l'aveugle"),
    "mistake-labels.jsonl": (BOOK, "les causes d'erreur de SES décisions"),
    "weekly-rituals.jsonl": (BOOK, "ses rituels de la semaine et leurs leçons"),
    "decision-review.json": (BOOK, "sa revue des décisions"),
    "wall-of-shame.json": (BOOK, "le mur de ses écarts"),
    "retractations.json": (BOOK, "ses rétractations datées"),
    "technical-drawings.json": (BOOK, "ses dessins sur les graphiques"),
    "verified-holdings.json": (BOOK, "archive de compatibilité de ses détentions"),
    "sold-listings.json": (BOOK, "la place des titres qu'il a vendus"),
    "watchlist-tv.json": (BOOK, "sa liste de candidats"),
    "watchlist-tradingview-2026-07-18.md": (BOOK, "piste datée tirée de sa liste"),
    "health-universe.json": (BOOK, "univers santé issu de sa liste TradingView"),
    "health-watchlist-classification.json": (BOOK, "classement de sa liste santé"),
    "instrument-themes.json": (BOOK, "thèmes attribués à SES fiches"),
    "rotation-research-context.json": (BOOK, "contexte de ses recherches de rotation"),
    "tripwires.json": (BOOK, "ses niveaux pré-engagés de topics"),
    "target-allocation.json": (BOOK, "son portefeuille visé"),
    "portfolio-policy.json": (BOOK, "ses réglages du livre (plafonds, taille)"),
    "performance-concordance.json": (BOOK, "concordance de SA performance avec IBKR"),
    "ai-sale-2026-07-17.md": (BOOK, "piste datée de son livre"),
    "draft-instrument-research-*.md": (BOOK, "brouillons de recherche sur ses lignes"),
    "postmortem-*.md": (BOOK, "post-mortems datés de SES décisions (cycles clos, coûts chiffrés)"),
    "bet-review-*.md": (BOOK, "revues datées de SES paris : thèmes, véhicules, risque, ce qui manque"),
    "opportunities-*.md": (BOOK, "chasses datées d'opportunités : situations spéciales, dérive après publication"),
    "risk-review-*.md": (BOOK, "préparations datées des décisions de risque : alerte de régime, réexamen du livre"),
    "instruments-to-add.json": (BOOK, "sa file d'instruments à ajouter"),
    "instruments-to-add-*.json": (BOOK, "ses files datées d'instruments à ajouter"),
    "instruments-queue-*.json": (BOOK, "ses files datées d'instruments"),
    "BOOK.md": (BOOK, "le document de son livre : profil, doctrine précisée, topics, décisions (data_root.book_doc)"),
    "owner.json": (BOOK, "le nom du propriétaire du livre (data_root.owner_label)"),

    "schedules.json": (BOOK, "les ordonnanceurs de SON installation"),
    "price-collection-baseline.json": (BOOK, "mesure de la collecte de SON cache"),
    "price-collection-parity.json": (BOOK, "parité de la collecte de SON cache"),
    "price-collection-production-pass.json": (BOOK, "passe de production de SON cache"),
    "event-driven-refresh-validation.json": (BOOK, "validation sur SON installation"),
    "eodhd-concordance.json": (BOOK, "concordance de SON abonnement EODHD, non revendable"),
    "eodhd-guards.json": (BOOK, "verdicts des gardes sur SON abonnement EODHD, non revendable"),
    "narration-baseline.json": (BOOK, "ligne de base de SES narrations"),
    "brief-log-baseline.json": (BOOK, "ligne de base de SES briefs"),
    "brief-sweep-method.json": (METHOD, "sources balayées par le brief et suites admises"),
    "brief-topics.json": (BOOK, "SES sujets ouverts par les briefs et leur suite"),
    "maintenance.md": (BOOK, "journal de maintenance de son dépôt"),
    "book-separation-plan.md": (BOOK, "mesure et plan de sortie de son livre hors du dépôt produit"),

    "product-strategy.md": (BOOK, "sa stratégie commerciale"),
    "competitor-ideas-plan.md": (BOOK, "son plan tiré des concurrents"),

    "architecture.md": (METHOD, "la forme du système"),
    "backend-api.md": (METHOD, "interroger le backend du dashboard, par curl ou par le MCP"),
    "data-sources.md": (METHOD, "les sources et leurs pièges"),
    "doctrine-buy.md": (METHOD, "doctrine d'achat"),
    "doctrine-levels.md": (METHOD, "doctrine des niveaux"),
    "doctrine-plans.md": (METHOD, "contrat des plans"),
    "guards.md": (METHOD, "les gardes"),
    "vocabulary.md": (METHOD, "le vocabulaire"),
    "workflow.md": (METHOD, "l'ordre des étapes"),
    "findings.md": (METHOD, "motifs établis, pas des mesures du livre"),
    "method-position-analysis.md": (METHOD, "méthode d'analyse d'une ligne"),
    "technical-patterns.md": (METHOD, "figures techniques"),
    "macroeconomics.md": (METHOD, "doctrine macro"),
    "macro-data.md": (METHOD, "données macro"),
    "macro-review.md": (METHOD, "revue macro"),
    "macro-series.json": (METHOD, "séries macro suivies"),
    "price-collection-plan.md": (METHOD, "plan de collecte des prix"),
    "event-driven-refresh-plan.md": (METHOD, "plan du rafraîchissement événementiel"),
    "postures.md": (METHOD, "vue GÉNÉRÉE des mesures de filtres"),
    "postures.jsonl": (METHOD, "mesures datées des filtres de la méthode"),
    "postures-baseline.json": (METHOD, "ligne de base des mesures de filtres"),
    "short-interest-measure.json": (METHOD, "mesure du filtre de vente à découvert"),
    "baskets.json": (METHOD, "paniers de marché"),
    "basket-contracts.json": (METHOD, "contrats des paniers"),
    "basket-members-tv.json": (METHOD, "membres des paniers"),
    "bar-rulings.json": (METHOD, "barres de prix arbitrées, faits de marché"),
    "splits.json": (METHOD, "registre des splits"),
    "compositions-exemptes.json": (METHOD, "ce qui n'a pas de composition"),
    "compositions-liveness.json": (METHOD, "sources de composition des fonds"),
    "market-identity.json": (METHOD, "identités de marché"),
    "filing-rulings.json": (BOOK, "ses arbitrages des dépôts SEC de SES lignes (reclassé le 2026-10-17)"),
    "clinical-base-rates.json": (METHOD, "taux de base cliniques"),
    "entry-checklist.json": (METHOD, "liste de contrôle d'entrée"),
    "event-checklists.json": (METHOD, "listes de contrôle d'événement"),
    "score-rubric.json": (METHOD, "rubrique de score"),
    "signal-scorecard-rubric.json": (METHOD, "rubrique du bilan des signaux"),
    "stress-scenarios.json": (METHOD, "scénarios de stress"),
    "research-taxonomy.json": (METHOD, "taxonomie documentaire"),
    "tradingview-taxonomy.json": (METHOD, "taxonomie TradingView"),
    "trading-calendar-exceptions.json": (METHOD, "exceptions du calendrier"),
    "political-events.json": (METHOD, "événements politiques, faits publics"),
    "x-accounts.json": (METHOD, "comptes X suivis par la veille"),

    "ratio-universe.json": (BOOK, "son manifeste entier : univers suivi, possession, ses listes"),
    "ratio-universe-method.json": (METHOD, "graine GÉNÉRÉE de l'univers de marché, sans possession"),
    "tripwires-method.json": (METHOD, "alertes de régime livrées, sans ses décisions ni ses mesures"),
    "regime-states-method.json": (METHOD, "états du marché et règle figée de leur mesure"),
    "portfolio-policy-method.json": (METHOD, "réglages par défaut livrés (panier, taille, mesures de revue)"),
}


def kind_of(name: str) -> str | None:
    """La nature d'une entrée de `references/`, ou None si elle n'est pas classée."""
    if name in LAYOUT:
        return LAYOUT[name][0]
    for pattern, (kind, _reason) in LAYOUT.items():
        if any(ch in pattern for ch in "*?[") and fnmatch.fnmatch(name, pattern):
            return kind
    return None


def book_names() -> set[str]:
    """Les noms exacts (sans motif) classés `book`."""
    return {name for name, (kind, _r) in LAYOUT.items() if kind == BOOK and not any(c in name for c in "*?[")}


def unclassified(directory: pathlib.Path = REFERENCES) -> list[str]:
    """Les entrées présentes que le registre ne classe pas."""
    return sorted(p.name for p in directory.iterdir() if not p.name.startswith(".") and kind_of(p.name) is None)


def dead_entries(directory: pathlib.Path = REFERENCES) -> list[str]:
    """Les entrées du registre qui ne désignent plus rien."""
    present = [p.name for p in directory.iterdir()]
    judged = LAYOUT
    if directory == REFERENCES:
        import data_root
        book = data_root.book_refs()
        if book.resolve() != directory.resolve() and book.is_dir():
            present += [p.name for p in book.iterdir()]
        if not data_root.book_is_present():
            judged = {name: entry for name, entry in LAYOUT.items() if entry[0] != BOOK}
    return sorted(name for name in judged
                  if not any(fnmatch.fnmatch(p, name) for p in present))


def judged(name: str) -> bool:
    """Une entrée nommée se juge-t-elle ici ? Toujours, sauf une entrée `book` sans livre."""
    import data_root
    return kind_of(name) != BOOK or data_root.book_is_present()


def stale_book_copies() -> list[str]:
    """Les entrées `book` encore présentes sur le disque sous le `references/` du produit"""
    import data_root
    if not data_root.book_is_external():
        return []
    return sorted(p.name for p in REFERENCES.iterdir() if kind_of(p.name) == BOOK)


def reference_files(pattern: str = "*") -> list[pathlib.Path]:
    """Les fichiers de `references/` au sens LOGIQUE : la méthode du produit, le livre là où il vit."""
    import data_root
    book = data_root.book_refs()
    if not book.is_dir() or book.resolve() == REFERENCES.resolve():
        return sorted(REFERENCES.glob(pattern))
    product = [p for p in REFERENCES.glob(pattern) if kind_of(p.name) != BOOK]
    return sorted(product + list(book.glob(pattern)), key=lambda p: p.name)





PERSONAL_PREFIXES = ("dashboard/backend/data/", "data/reports/")
KEEP_FILES = (".gitkeep",)







GITIGNORE = ROOT / ".gitignore"
GITIGNORE_START = "# >>> livre — généré par scripts/reference_layout.py --gitignore, ne pas éditer"
GITIGNORE_END = "# <<< livre"


def gitignore_block() -> str:
    """Les motifs qui ignorent le livre dans le dépôt produit."""
    lines = [GITIGNORE_START]
    lines += [f"/references/{name}" for name in sorted(n for n, (k, _r) in LAYOUT.items() if k == BOOK)]
    lines += [f"/{prefix}*" for prefix in PERSONAL_PREFIXES]
    lines += [f"!/{prefix}{keep}" for prefix in PERSONAL_PREFIXES for keep in KEEP_FILES]
    return "\n".join([*lines, GITIGNORE_END]) + "\n"


def gitignore_with_block(text: str) -> str:
    """`text` (un `.gitignore`) avec le bloc du livre à jour, ajouté s'il manque."""
    block = gitignore_block()
    if GITIGNORE_START in text and GITIGNORE_END in text:
        head, rest = text.split(GITIGNORE_START, 1)
        tail = rest.split(GITIGNORE_END, 1)[1].lstrip("\n")
        return head + block + tail
    return text.rstrip("\n") + "\n\n" + block


def personal_family(path: str) -> str | None:
    """La famille personnelle d'un chemin suivi (relatif au dépôt), ou None."""
    parts = path.split("/")
    if parts[0] == "references" and len(parts) >= 2 and kind_of(parts[1]) == BOOK:
        return "references/" + (parts[1] if len(parts) > 2 else "(fichiers du livre)")
    if parts[-1] in KEEP_FILES:
        return None
    for prefix in PERSONAL_PREFIXES:
        if path.startswith(prefix):
            rest = path[len(prefix):].split("/")
            return prefix + (rest[0] if len(rest) > 1 else "(fichiers racine)")
    return None


def tracked_personal_files(paths: list[str] | None = None) -> list[str]:
    """Les fichiers SUIVIS par Git qui appartiennent au livre ou à son installation."""
    if paths is None:
        import subprocess
        run = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, text=True, timeout=60)
        paths = [p for p in run.stdout.split("\0") if p]
    return sorted(p for p in paths if personal_family(p))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Classement de references/ : méthode livrée ou livre personnel.")
    parser.add_argument("--check", action="store_true",
                        help="rc 1 si une entrée n'est pas classée, est morte ou reste en copie figée du livre")
    parser.add_argument("--tracked", action="store_true",
                        help="compter, par famille, les fichiers du livre encore suivis par le dépôt produit")
    parser.add_argument("--gitignore", action="store_true",
                        help="réécrire le bloc du livre dans le .gitignore racine")
    args = parser.parse_args(argv)
    if args.gitignore:
        import atomic_file
        text = GITIGNORE.read_text(encoding="utf-8")
        updated = gitignore_with_block(text)
        if updated != text:
            atomic_file.write_text(GITIGNORE, updated)
        print(f".gitignore : bloc du livre {'réécrit' if updated != text else 'déjà à jour'}")
        return 0
    if args.tracked:
        import collections
        files = tracked_personal_files()
        families = collections.Counter(personal_family(p) for p in files)
        print(f"LIVRE SUIVI PAR LE DÉPÔT PRODUIT — {len(files)} fichier(s)")
        for family, count in sorted(families.items(), key=lambda item: -item[1]):
            print(f"  {count:6d}  {family}")
        return 0
    missing, dead, stale = unclassified(), dead_entries(), stale_book_copies()
    if not args.check:
        for kind in (METHOD, BOOK, MIXED):
            names = sorted(n for n, (k, _r) in LAYOUT.items() if k == kind)
            print(f"{KIND_LABELS[kind]} ({len(names)}) :")
            for name in names:
                print(f"  {name:42} {LAYOUT[name][1]}")
    for name in missing:
        print(f"⛔ non classé : {name} — le déclarer dans reference_layout.LAYOUT", file=sys.stderr)
    for name in dead:
        print(f"⛔ entrée morte : {name} — ne désigne plus rien", file=sys.stderr)
    for name in stale:
        print(f"⛔ copie figée du livre dans le produit : references/{name} — la déplacer hors du dépôt",
              file=sys.stderr)
    return 1 if (missing or dead or stale) else 0


if __name__ == "__main__":
    raise SystemExit(main())
