"""Le répertoire de données configuré — feuille sans dépendance du dépôt."""
from __future__ import annotations

import os
import pathlib

SKILL = pathlib.Path(__file__).resolve().parent.parent









LOCAL_CONFIG_NAME = "wallet.local.json"
DATA_ENV = "WALLET_DATA"


def _main_tree(root: pathlib.Path | None = None) -> pathlib.Path | None:
    """L'arbre principal quand `root` est un worktree Git, sinon `None`."""
    root = SKILL if root is None else root
    marker = root / ".git"
    try:
        if not marker.is_file():
            return None
        line = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not line.startswith("gitdir:"):
        return None
    gitdir = pathlib.Path(line.removeprefix("gitdir:").strip())
    gitdir = gitdir if gitdir.is_absolute() else (root / gitdir).resolve()
    return gitdir.parents[2] if gitdir.parent.name == "worktrees" else None


def local_config_file() -> pathlib.Path:
    """Le pointeur local de cette installation, qu'il existe ou non."""
    own = SKILL / LOCAL_CONFIG_NAME
    if own.exists():
        return own
    main = _main_tree()
    return main / LOCAL_CONFIG_NAME if main is not None else own


def _local_config() -> dict:
    import json
    try:
        loaded = json.loads(local_config_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _configured(env: str, key: str, default: pathlib.Path) -> pathlib.Path:
    if os.environ.get(env):
        return pathlib.Path(os.environ[env])
    value = _local_config().get(key)
    if isinstance(value, str) and value.strip():
        path = pathlib.Path(value.strip()).expanduser()
        return path if path.is_absolute() else SKILL / path
    return default


def repo_data_dir(root: pathlib.Path = SKILL) -> pathlib.Path:
    """Le dossier de données PAR DÉFAUT d'un dépôt, sans pointeur ni environnement."""
    return pathlib.Path(root) / "dashboard" / "backend" / "data"


def data_path() -> pathlib.Path:
    """Le répertoire de données CONFIGURÉ, sans exiger qu'il existe."""
    return _configured(DATA_ENV, "data", repo_data_dir())








PRICES_ENV = "WALLET_PRICES"




SERIES_SUBDIR = "series"


def prices_store() -> pathlib.Path:
    """Le magasin RÉEL du cache de prix (pointeur ou défaut), environnement ignoré :"""
    value = _local_config().get("prices")
    if isinstance(value, str) and value.strip():
        path = pathlib.Path(value.strip()).expanduser()
        return path if path.is_absolute() else SKILL / path
    return SKILL / "data" / "prices"


def series_store() -> pathlib.Path:
    """Le dossier RÉEL des séries `{conid}.json`, environnement ignoré."""
    return prices_store() / SERIES_SUBDIR


def prices_dir() -> pathlib.Path:
    """Les séries `{conid}.json` en usage : `WALLET_PRICES`, sinon le magasin réel."""
    if os.environ.get(PRICES_ENV):
        return pathlib.Path(os.environ[PRICES_ENV])
    return series_store()


def price_logs_dir() -> pathlib.Path:
    """Les journaux et états de collecte du cache : `WALLET_PRICES`, sinon la"""
    if os.environ.get(PRICES_ENV):
        return pathlib.Path(os.environ[PRICES_ENV])
    return prices_store()






BOOK_REFS_ENV = "WALLET_BOOK_REFS"


def book_refs() -> pathlib.Path:
    """Le dossier des références du LIVRE, sans exiger qu'il existe."""
    return _configured(BOOK_REFS_ENV, "book_refs", SKILL / "references")




BOOK_DOC_NAME = "BOOK.md"


def book_doc() -> pathlib.Path:
    """`BOOK.md` du livre, qu'il existe ou non."""
    return book_refs() / BOOK_DOC_NAME


REPORTS_ENV = "WALLET_REPORTS"


def reports_dir() -> pathlib.Path:
    """Les rapports de l'installation : quotidiens HTML, digests, enquêtes datées."""
    return _configured(REPORTS_ENV, "reports", SKILL / "data" / "reports")


FLEX_CONFIG_ENV = "WALLET_FLEX_CONFIG"


def flex_config_file() -> pathlib.Path:
    """Le fichier du jeton Flex (`webservice.json`)."""
    return _configured(FLEX_CONFIG_ENV, "flex_config", data_path() / "flex" / "webservice.json")


def book_repo() -> pathlib.Path | None:
    """La racine du dépôt Git du livre quand il vit hors du dépôt produit."""
    if not book_is_external():
        return None
    for candidate in (book_refs(), *book_refs().parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def book_is_present() -> bool:
    """Le livre a-t-il au moins une fiche ? Sinon c'est le produit au livre vide."""
    return any((book_refs() / "instruments").glob("*.json"))


def book_is_external() -> bool:
    """Le livre vit-il hors du `references/` du dépôt produit ?"""
    try:
        return book_refs().resolve() != (SKILL / "references").resolve()
    except OSError:
        return True




UNIVERSE_NAME = "ratio-universe.json"
UNIVERSE_SEED_NAME = "ratio-universe-method.json"


def universe_book_file() -> pathlib.Path:
    """Le manifeste personnel, où ÉCRIVENT ceux qui l'enrichissent."""
    return book_refs() / UNIVERSE_NAME


def universe_file() -> pathlib.Path:
    """Le manifeste à LIRE : le personnel s'il existe, sinon la graine livrée."""
    own = universe_book_file()
    return own if own.exists() else SKILL / "references" / UNIVERSE_SEED_NAME


def universe_seed_file() -> pathlib.Path:
    """La graine livrée de l'univers de marché."""
    return SKILL / "references" / UNIVERSE_SEED_NAME




TRIPWIRES_NAME = "tripwires.json"
TRIPWIRES_SEED_NAME = "tripwires-method.json"
POLICY_NAME = "portfolio-policy.json"
POLICY_SEED_NAME = "portfolio-policy-method.json"
SEEDS = {UNIVERSE_SEED_NAME: UNIVERSE_NAME, TRIPWIRES_SEED_NAME: TRIPWIRES_NAME,
         POLICY_SEED_NAME: POLICY_NAME}


def _seeded_file(book_name: str, seed_name: str) -> pathlib.Path:
    own = book_refs() / book_name
    return own if own.exists() else SKILL / "references" / seed_name


def tripwires_file() -> pathlib.Path:
    """Les niveaux à LIRE : les siens s'ils existent, sinon les alertes de régime livrées."""
    return _seeded_file(TRIPWIRES_NAME, TRIPWIRES_SEED_NAME)


def policy_file() -> pathlib.Path:
    """La politique à LIRE : la sienne si elle existe, sinon les réglages par défaut livrés."""
    return _seeded_file(POLICY_NAME, POLICY_SEED_NAME)


def tripwires_book_file() -> pathlib.Path:
    """Ses niveaux, où ÉCRIVENT ceux qui en ajoutent."""
    return book_refs() / TRIPWIRES_NAME


def seeded_target(read_path) -> pathlib.Path:
    """Où écrire après avoir lu `read_path` : le même fichier, sauf une graine,"""
    read_path = pathlib.Path(read_path)
    for seed_name, book_name in SEEDS.items():
        if read_path == SKILL / "references" / seed_name:
            return book_refs() / book_name
    return read_path


def seeded_source(read_path) -> pathlib.Path:
    """Ce qu'un écrivain doit relire : le fichier du livre s'il est né depuis l'import."""
    target = seeded_target(read_path)
    return target if target != pathlib.Path(read_path) and target.exists() else pathlib.Path(read_path)


def universe_target(read_path) -> pathlib.Path:
    """Où écrire après avoir lu `read_path` : le même fichier, sauf la graine."""
    read_path = pathlib.Path(read_path)
    return universe_book_file() if read_path == universe_seed_file() else read_path


def universe_source(read_path) -> pathlib.Path:
    """Ce qu'un écrivain doit relire : le personnel s'il est né depuis l'import."""
    read_path = pathlib.Path(read_path)
    if read_path == universe_seed_file() and universe_book_file().exists():
        return universe_book_file()
    return read_path


def has_backend() -> bool:
    """L'installation porte-t-elle le backend du dashboard (Gateway, Flex, ledger) ?"""
    return (SKILL / "dashboard" / "backend" / "app.py").exists()





OWNER_DEFAULT = "l'investisseur"


def owner_label() -> str:
    """Le nom du propriétaire du livre, ou « l'investisseur »."""
    import json
    path = book_refs() / "owner.json"
    try:
        name = json.loads(path.read_text(encoding="utf-8")).get("name")
    except (OSError, ValueError, AttributeError):
        return OWNER_DEFAULT
    return name.strip() if isinstance(name, str) and name.strip() else OWNER_DEFAULT
