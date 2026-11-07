"""Catégories des instruments : définition unique, libellés et allocation."""
from __future__ import annotations
import data_root

from dataclasses import dataclass
import argparse
import json
from pathlib import Path


@dataclass(frozen=True)
class Category:
    """Libellé français et rattachement exclusif dans Allocation."""

    label: str
    bucket: str | None
    pocket: str | None = None




HEALTH_BUCKET = 'Santé & biotech'

CATEGORIES = {
    'therapeutic': Category('Thérapeutiques', HEALTH_BUCKET, 'Thérapeutique clinique'),
    'pharma': Category('Pharma', HEALTH_BUCKET, 'Pharma commerciale'),
    'diagnostics': Category('Diagnostic', HEALTH_BUCKET, 'Outils & diagnostic'),
    'liquid-biopsy': Category('Biopsie liquide en oncologie', HEALTH_BUCKET, 'Outils & diagnostic'),
    'cancer-diagnostics': Category('Diagnostic moléculaire du cancer', HEALTH_BUCKET, 'Outils & diagnostic'),
    'transplant-diagnostics': Category('Diagnostic de transplantation', HEALTH_BUCKET, 'Outils & diagnostic'),
    'genetic-diagnostics': Category('Diagnostic génétique', HEALTH_BUCKET, 'Outils & diagnostic'),
    'autoimmune-diagnostics': Category('Diagnostic des maladies auto-immunes', HEALTH_BUCKET, 'Outils & diagnostic'),
    'nuclear-diagnostics': Category('Diagnostic nucléaire', HEALTH_BUCKET, 'Outils & diagnostic'),


    'sequencing': Category('Séquençage', HEALTH_BUCKET, 'Outils & diagnostic'),
    'single-cell-spatial': Category('Génomique unicellulaire et spatiale', HEALTH_BUCKET, 'Outils & diagnostic'),
    'synthetic-biology': Category('Biologie synthétique / ADN', HEALTH_BUCKET, 'Outils & diagnostic'),
    'lab-instruments': Category('Instruments de laboratoire et analyse', HEALTH_BUCKET, 'Outils & diagnostic'),
    'bioprocessing': Category('Bioproduction', HEALTH_BUCKET, 'Outils & diagnostic'),



    'drug-discovery': Category('Découverte de médicaments / IA', HEALTH_BUCKET, 'Thérapeutique clinique'),
    'healthcare-services': Category('Services de santé', HEALTH_BUCKET, 'Services de santé'),
    'medtech': Category('Dispositifs médicaux', HEALTH_BUCKET, 'Medtech / dispositifs'),
    'etf-health': Category('ETF santé', HEALTH_BUCKET, 'ETF santé'),
    'tech': Category('Tech / IA', 'Technologie', None),
    'etf-industrials': Category('ETF industrie', 'Industrie', None),
    'etf-tech': Category('ETF tech', 'Technologie', None),
    'financials': Category('Financières', 'Financières', None),
    'etf-financials': Category('ETF financières', 'Financières', None),
    'etf-china': Category('ETF Chine', 'Actions pays', None),
    'etf-israel': Category('ETF Israël', 'Actions pays', None),
    'etf-metals': Category('ETF métaux', 'Matières premières', None),
    'etf-materials': Category('ETF matériaux', 'Matières premières', None),
    'mining': Category('Minières', 'Matières premières', None),
    'etf-commodities': Category('ETF matières premières', 'Matières premières', None),
    'agtech': Category('AgTech — technologie, semences et équipement agricoles', 'Agriculture', 'AgTech'),
    'agro': Category('Agro-industrie / producteurs', 'Agriculture', 'Agro-industrie / producteurs'),
    'etf-agri': Category('Futures agricoles diversifiés', 'Agriculture', 'Futures agricoles diversifiés'),
    'agri-crop': Category('Futures agricoles mono-culture', 'Agriculture', 'Futures mono-culture'),
    'etf-realestate': Category('ETF immobilier', 'Immobilier', None),
    'etf-value': Category('ETF value / FCF', 'Diversifié / valeur', None),
    'market': Category('Marché large (US)', 'Diversifié / valeur', None),
    'energy': Category('Énergie', 'Énergie', None),
    'utilities': Category('Services publics', 'Reste', None),
    'industrial': Category('Industrie', 'Industrie', None),
    'telecom': Category('Télécom / satellite', 'Reste', None),
    'consumer': Category('Consommation', 'Reste', None),
    'cannabis': Category('Cannabis', 'Reste', None),
    'crypto': Category('Crypto', 'Crypto', None),
    'travel': Category('Voyage', 'Reste'),
    'business-services': Category('Services aux entreprises', 'Reste'),
    'etf-country': Category('ETF pays', 'Actions pays'),
    'etf-global': Category('ETF zones / monde', 'Actions pays'),
    'etf-bonds': Category('ETF obligataires', 'Obligations'),
    'macro-index': Category('Indice de taux ou volatilité', None),
    'currency': Category('Devises', 'Devises'),
    'communication': Category('Communication / médias', 'Reste'),
    'reit': Category('Société immobilière cotée', 'Immobilier'),
}


ALIASES = {"industrie": "industrial", "voyage": "travel"}

BUCKET_ORDER = [HEALTH_BUCKET, "Technologie", "Financières", "Industrie", "Énergie",
                "Agriculture", "Actions pays", "Matières premières", "Immobilier",
                "Obligations", "Devises", "Diversifié / valeur", "Crypto", "Reste"]
POCKET_ORDER = ["Thérapeutique clinique", "ETF santé", "Outils & diagnostic",
                "Pharma commerciale", "Services de santé", "Medtech / dispositifs",
                "AgTech", "Agro-industrie / producteurs",
                "Futures agricoles diversifiés", "Futures mono-culture"]


def normalize_category(value: str | None) -> str | None:
    """Accepte une absence et les anciens alias précis ; refuse tout groupe vague."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("La catégorie doit être un code texte ou null.")
    normalized = ALIASES.get(value, value)
    if normalized not in CATEGORIES:
        raise ValueError(f"Catégorie inconnue : {value!r}. Consulter instrument_categories.CATEGORIES.")
    return normalized











DEFAULT_REFERENCE = "SPY"
REFERENCE_ETFS: dict[str, str | None] = {
    'therapeutic': 'XBI', 'drug-discovery': 'XBI', 'pharma': 'XPH',
    'diagnostics': 'XLV', 'liquid-biopsy': 'XLV', 'cancer-diagnostics': 'XLV',
    'transplant-diagnostics': 'XLV', 'genetic-diagnostics': 'XLV',
    'autoimmune-diagnostics': 'XLV', 'nuclear-diagnostics': 'XLV',
    'sequencing': 'XLV', 'single-cell-spatial': 'XLV', 'synthetic-biology': 'XLV',
    'lab-instruments': 'XLV', 'bioprocessing': 'XLV',
    'healthcare-services': 'IHF', 'medtech': 'IHI', 'etf-health': 'XLV',
    'tech': 'XLK', 'etf-tech': 'XLK', 'etf-industrials': 'XLI', 'industrial': 'XLI',
    'business-services': 'XLI', 'financials': 'XLF', 'etf-financials': 'XLF',
    'etf-china': 'MCHI', 'etf-israel': 'EIS', 'etf-metals': 'XME', 'mining': 'XME',
    'etf-materials': 'XLB', 'etf-commodities': 'DBC', 'agtech': 'MOO', 'agro': 'MOO',
    'etf-agri': 'DBA', 'agri-crop': 'DBA', 'etf-realestate': 'XLRE', 'reit': 'XLRE',
    'etf-value': 'SPY', 'market': 'SPY', 'energy': 'XLE', 'utilities': 'XLU',
    'telecom': 'XLC', 'communication': 'XLC', 'consumer': 'XLY', 'cannabis': 'MSOS',
    'crypto': 'IBIT', 'travel': 'JETS', 'etf-country': 'ACWI', 'etf-global': 'ACWI',
    'etf-bonds': 'BND', 'macro-index': None, 'currency': None,
}


def reference_etf(category: str | None) -> str | None:
    """Le repère de cours d'une catégorie ; `DEFAULT_REFERENCE` sans catégorie."""
    if category is None:
        return DEFAULT_REFERENCE
    return REFERENCE_ETFS.get(ALIASES.get(category, category), DEFAULT_REFERENCE)



UNCLASSIFIED_POCKET = "Non classé"


def pocket_label(category: str | None) -> str:
    """La poche d'Allocation d'une catégorie, sinon son seau ; « Non classé » sans catégorie."""
    entry = CATEGORIES.get(ALIASES.get(category or "", category or ""))
    if entry is None:
        return UNCLASSIFIED_POCKET
    return entry.pocket or entry.bucket or UNCLASSIFIED_POCKET


CATEGORY_LABELS = {key: entry.label for key, entry in CATEGORIES.items()}
ALLOCATION_BUCKETS = {key: (entry.bucket, entry.pocket) for key, entry in CATEGORIES.items()
                      if entry.bucket is not None}
for alias, canonical in ALIASES.items():
    CATEGORY_LABELS[alias] = CATEGORY_LABELS[canonical]
    if canonical in ALLOCATION_BUCKETS:
        ALLOCATION_BUCKETS[alias] = ALLOCATION_BUCKETS[canonical]


def audit(sheets: Path) -> tuple[list[str], list[str]]:
    """Catégories hors contrat et fiches restant explicitement à classer."""
    invalid, unclassified = [], []
    for path in sorted(sheets.glob("*.json")):
        sheet = json.loads(path.read_text(encoding="utf-8"))
        value = (sheet.get("identity") or {}).get("category")
        if value is None:
            unclassified.append(path.stem)
        elif not isinstance(value, str) or value not in CATEGORIES:
            invalid.append(f"{path.stem} : {value!r}")
    return invalid, unclassified


def main() -> int:
    parser = argparse.ArgumentParser(description="Catégories communes des fiches et d'Allocation.")
    parser.add_argument("--check", action="store_true", help="contrôler toutes les fiches")
    args = parser.parse_args()
    if not args.check:
        for code, definition in CATEGORIES.items():
            print(f"{code:<24} {definition.label} → {definition.bucket or 'hors allocation'}"
                  + (f" / {definition.pocket}" if definition.pocket else ""))
        return 0
    invalid, unclassified = audit(data_root.book_refs() / "instruments")
    print(f"{len(invalid)} catégorie(s) hors contrat ; {len(unclassified)} fiche(s) à classer.")
    for issue in invalid:
        print(f"  ERREUR : {issue}")
    if unclassified:
        print("  À classer : " + ", ".join(unclassified))
    return int(bool(invalid))


if __name__ == "__main__":
    raise SystemExit(main())
