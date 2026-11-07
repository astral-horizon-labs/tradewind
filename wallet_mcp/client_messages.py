"""Les messages de la loi des plans, rendus en anglais au client de Tradewind.

POURQUOI (2026-11-07, décision du propriétaire). Le MCP client parle anglais de bout en
bout. Ses refus de plan viennent pourtant de `decision_schema` et de `tripwires`, la loi
partagée avec le dashboard du propriétaire, qui reste française : traduire là-bas
casserait son livre. On traduit donc à la FRONTIÈRE, ici, comme `client_book.english()`
le fait pour `flex_snapshot`.

Remplacements par motifs, appliqués dans l'ordre (le plus précis d'abord). Les
guillemets français deviennent des guillemets droits avant tout le reste, si bien que
les motifs suivants lisent `"…"`. `tests/test_client_messages.py` extrait chaque gabarit
de message des deux modules et échoue si l'un d'eux sort encore en français : un
message neuf de la loi exige sa ligne ici.
"""
from __future__ import annotations

import re

_V = r"(.+?)"

#: (motif, remplacement) ; `\1`, `\2`… reprennent les valeurs du message d'origine.
RULES: tuple[tuple[str, str], ...] = (
    (r"«\s*(.*?)\s*»", r'"\1"'),
    (r" : ", ": "),
    # ---- aide du format court (decision_schema.COMPACT_HELP) ----
    (r'forme attendue: "1W < 254\.7 \(mémoire\) \[sortie\] sortie complète" ; "sma10" et '
     r'"trail19\.2" remplacent le nombre pour une règle calculée ; le rôle entre crochets '
     r"\(sortie, allègement, renfort, alerte, revue\) est déduit de l'action s'il manque",
     'expected form: "1W < 254.7 (memory) [exit] full exit"; "sma10" and "trail19.2" replace '
     "the number for a computed rule; the effect in brackets (exit, trim, add, warn, review) "
     "is inferred from the action when missing"),
    (r"une date ISO AAAA-MM-JJ, ou catalyst:N \(la N-ième échéance de facts\.catalysts\)",
     "an ISO date YYYY-MM-DD, or catalyst:N (item N of facts.catalysts)"),
    (r"\[(mémoire|rond|filet)\]", lambda m: {"mémoire": "[memory]", "rond": "[round]",
                                            "filet": "[net]"}[m.group(1)]),
    # ---- niveaux ----
    (r"un niveau doit être un objet", "a level must be an object"),
    (r'champ "' + _V + r'" manquant dans plan\.levels', r'field "\1" missing from plan.levels'),
    (r'champ "' + _V + r'" manquant', r'field "\1" missing'),
    (r'(bar|op|trail\.rule|effect|set_by) "' + _V + r'" inconnu', r'\1 "\2" unknown'),
    (r'method "' + _V + r'" hors doctrine', r'method "\1" outside the method'),
    (r"il faut EXACTEMENT un seuil px\|trail\|sma \(trouvé: aucun\)",
     "exactly ONE threshold px|trail|sma is required (found: none)"),
    (r"il faut EXACTEMENT un seuil px\|trail\|sma", "exactly ONE threshold px|trail|sma is required"),
    (r"px non numérique", "px is not a number"),
    (r"(trail|arm|`arm`) doit être \{op: <\|>, px: nombre\}", r"\1 must be {op: <|>, px: number}"),
    (r"(trail|decision) doit être un objet", r"\1 must be an object"),
    (r"trail\.seed doit être un nombre", "trail.seed must be a number"),
    (r"trail\.confirm doit être un entier >= 1", "trail.confirm must be an integer >= 1"),
    (r"(`?trail`?) n'a de sens qu'avec op \"<\" — un palier qui monte est un PLANCHER, pas une cible",
     r'\1 only makes sense with op "<" — a rising step is a FLOOR, not a target'),
    (r"sma\.window doit être un entier (>=|≥) 2", r"sma.window must be an integer \1 2"),
    (r'(`?arm`?) sans ("since"|`since`) — un armement doit dater de la naissance du suivi'
     r"(?: \(activated_on\))?, sinon l'historique d'avant-plan le déclenche(?: \(voir activated_on\))?",
     r"\1 without \2 — an arming must date from when tracking began (activated_on), "
     "otherwise the history from before the plan triggers it"),
    (r'fraction n\'a de sens qu\'avec effect "trim"', 'fraction only makes sense with effect "trim"'),
    (r"fraction doit être un nombre entre 0 et 1 exclus", "fraction must be a number strictly between 0 and 1"),
    # ---- dates ----
    (_V + r" doit être une date ISO AAAA-MM-JJ", r"\1 must be an ISO date YYYY-MM-DD"),
    (_V + r" n'est pas une date du calendrier", r"\1 is not a calendar date"),
    (r'evaluate_on "' + _V + r'" hors contrat', r'evaluate_on "\1" outside the contract'),
    (r"evaluate_on " + _V + r" — l'échéance pointée n'a pas de date ISO \((.*?)\): le jugement en "
     r"exige une ; écrire la date \(AAAA-MM-JJ\) ou pointer une échéance datée",
     r"evaluate_on \1 — the pointed item has no ISO date (\2): the judgment needs one; write the "
     "date (YYYY-MM-DD) or point to a dated item"),
    # ---- critères et causes ----
    (r'un critère "cash" exige threshold \{min: montant > 0\}',
     'a "cash" criterion requires threshold {min: amount > 0}'),
    (r'un critère "dilution" exige threshold \{max_shares: n\} ou \{max_pct: p, base_shares: n\}',
     'a "dilution" criterion requires threshold {max_shares: n} or {max_pct: p, base_shares: n}'),
    (r'le seuil d\'un critère "' + _V + r'" est une phrase, la machine ne le mesure pas',
     r'the threshold of a "\1" criterion is a sentence, the machine does not measure it'),
    (r"(criteria|failure_modes|levels|proxy_levels) doit être une liste", r"\1 must be a list"),
    (r"un critère doit être un objet", "a criterion must be an object"),
    (r"id manquant ou illisible \(minuscules ASCII, chiffres, tirets\)",
     "id missing or unreadable (lowercase ASCII, digits, hyphens)"),
    (r'id "' + _V + r'" en double', r'duplicate id "\1"'),
    (r'"expect" vide — ce qui doit être vrai, en une phrase', '"expect" empty — what must be true, in one sentence'),
    (r"champ\(s\) hors contrat", "field(s) outside the contract"),
    (r"pillar doit être un entier de " + _V + r" à " + _V + r"$", r"pillar must be an integer from \1 to \2"),
    (r"pilier " + _V + r" en double", r"duplicate pillar \1"),
    (r"\) — un statut se DÉCLARE", ") — a status is DECLARED"),
    (r"un pilier exige son capteur lié \(sensor\)", "a pillar requires its linked sensor (sensor)"),
    (r'un critère daté exige "by", sa date ISO', 'a dated criterion requires "by", its ISO date'),
    (r'"if_missed" vide — ce que la relecture devra trancher', '"if_missed" empty — what the review will have to decide'),
    (r"une cause doit être un objet", "a cause must be an object"),
    (r'"cause" vide — pourquoi la ligne aurait échoué, en une phrase',
     '"cause" empty — why the holding would have failed, in one sentence'),
    (r"\) — un ordre, jamais une probabilité", ") — an order, never a probability"),
    (r'"no_sensor_reason" est une phrase', '"no_sensor_reason" is a sentence'),
    (r'"no_sensor_reason" contredit le capteur ' + _V + r" déjà pointé",
     r'"no_sensor_reason" contradicts the sensor \1 already pointed to'),
    (r'une cause "haute" pointe un niveau ou une échéance \(level:N, catalyst:N\), ou dit pourquoi '
     r"elle ne le peut pas \(no_sensor_reason\)",
     'a "high" cause points to a level or a dated item (level:N, catalyst:N), or says why it '
     "cannot (no_sensor_reason)"),
    # ---- décision ----
    (r'(status|horizon|role|kind|likelihood) "' + _V + r'" hors contrat', r'\1 "\2" outside the contract'),
    (_V + r" est de la prose, une chaîne", r"\1 is prose, a string"),
    (r'"' + _V + r'" n\'appartient pas au bloc decision — une probabilité s\'écrit au registre des '
     r"prévisions \(scripts/forecasts\.py\)",
     r'"\1" does not belong in the decision block — a probability goes to the forecast register '
     "(scripts/forecasts.py)"),
    (r"une décision active exige un horizon", "an active plan requires a horizon"),
    (r'une décision active sans aucun niveau exige "no_levels_reason" — pourquoi aucun capteur '
     r"n'est armé",
     'an active plan without any level requires "no_levels_reason" — why no sensor is armed'),
    (r'un trail ou un arm sans "since" exige activated_on, sinon le niveau n\'a pas de date de naissance',
     'a trail or an arm without "since" requires activated_on, otherwise the level has no birth date'),
    (r'une préparation exige "thesis"', 'a draft requires "thesis"'),
    (r'une décision soldée exige "closed_on", la date de la vente',
     'a closed plan requires "closed_on", the date of the sale'),
    (r'"closed_on" n\'a de sens que sur une décision soldée \(status closed\)',
     '"closed_on" only makes sense on a closed plan (status closed)'),
    (r'"' + _V + r'" vide sur une décision active', r'"\1" empty on an active plan'),
    # ---- saisies ----
    (r"verdict inconnu: " + _V + r" \((.*?), ou tient\|en partie changée\|invalidée\)",
     r"unknown verdict: \1 (\2)"),
    (r"horizon inconnu: " + _V + r" \(long\|short, ou long terme\|court terme\|tactique\)",
     r"unknown horizon: \1 (long|short)"),
    (r"(statut|rôle) inconnu: " + _V + r" \((.*?), ou leurs libellés français\)",
     lambda m: f"unknown {'status' if m.group(1) == 'statut' else 'role'}: {m.group(2)} ({m.group(3)})"),
    (r"rôle de niveau inconnu: " + _V + r" \((.*?), ou sortie\|allègement\|renfort\|alerte\|revue\)",
     r"unknown level effect: \1 (\2)"),
    (r"--evaluate-on " + _V + r": aucune échéance datée à venir dans facts\.catalysts — écrire la date",
     r"--evaluate-on \1: no upcoming dated item in facts.catalysts — write the date"),
    (r"niveau illisible: ", "unreadable level: "),
    (r"fenêtre de SMA non entière: ", "SMA window is not an integer: "),
    # ---- évaluation d'un niveau (tripwires) ----
    (_V + r" absent de ratio-universe\.json — ajouter le conid au manifeste",
     r"\1 missing from ratio-universe.json — add the conid to the manifest"),
    (r"niveau\(x\) de plan invérifiable\(s\) — ", "plan level(s) cannot be checked — "),
    (r"aucune période finie en cache", "no settled period in the cache"),
    (r" \(partiel " + _V + r" au " + _V + r"\)", r" (partial \1 on \2)"),
    (r"suiveur NON ARMÉ — aucune clôture " + _V + r" depuis " + _V + r" ; seuil " + _V
     + r" inerte tant que la cassure n'a pas eu lieu",
     r"trailing level NOT ARMED — no \1 close since \2; \3 threshold inert until the breakout"),
    (r" \[armé depuis " + _V + r"\]", r" [armed since \1]"),
    (r"— clôture ", "— close "),
    (r"clôture (\S+)(?= =|$)", r"\1 close"),
    (r"cache " + _V + r" absent pour " + _V + r" \(conid", r"\1 cache missing for \2 (conid"),
    (r"cache 1D de " + _V + r" sans borne de clôture réglée — impossible de distinguer une barre "
     r"finale d'un instantané intrajournalier\. Tirer via refresh_close\.py\.",
     r"1D cache of \1 has no settled-close boundary — a final bar cannot be told from an intraday "
     "snapshot. Refresh the series."),
    (r"cache " + _V + r" de " + _V + r" périmé \(" + _V + r" j\) — tirer via --stale",
     r"\1 cache of \2 is stale (\3 d) — refresh the series"),
    (r"cache " + _V + r" de " + _V + r" EN RETARD de (\S+) \S+ réglée\(s\) — le "
     r"seuil serait évalué sur une période périmée \(âge " + _V + r" j, sous le seuil de " + _V
     + r" j: l'ancienne garde se taisait\)\. Tirer via --stale\.",
     r"\1 cache of \2 is \3 settled close(s) BEHIND — the threshold would be checked on a stale "
     r"period (age \4 d, limit \5 d). Refresh the series."),
    (_V + r" période\(s\) réglée\(s\) en cache pour une SMA" + _V + r" — fenêtre incomplète, pas de "
     r"moyenne partielle",
     r"\1 settled period(s) in the cache for an SMA\2 — incomplete window, no partial average"),
    # ---- alertes de régime (tripwires.topic_value, check) ----
    (r"(\S+) (sous|au-dessus de) sa SMA",
     lambda m: f"{m.group(1)} {'below' if m.group(2) == 'sous' else 'above'} its SMA"),
    (r"(\S+) sous SMA", r"\1 below SMA"),
    (r"pas de semaine finie commune en cache", "no common finished week in the cache"),
    (r"dernière semaine finie ", "last finished week "),
    (r"semaine finie inconnue", "finished week unknown"),
    (r"semaine finie ", "finished week "),
    (r"dernier mois complet", "last full month"),
    (r"pas de mois complet en cache", "no full month in the cache"),
    (r"\(partiel ", "(partial "),
    (r", levée après " + _V + r" clôtures consécutives", r", released after \1 consecutive closes"),
    (r" ; dernières ", "; latest "),
    (r": jambe ", ": leg "),
    (r"aucune NAV quotidienne", "no daily NAV"),
    (r"NAV du " + _V + r", sommet du ", r"NAV of \1, peak of "),
    (r"LIVRE baisse depuis le sommet", "BOOK drawdown from peak"),
    # ---- tirage Flex (flex_webservice) ----
    (r"Flex Web Service erreur ", "Flex Web Service error "),
    (r"(SendRequest|GetStatement) injoignable", r"\1 unreachable"),
    (r"SendRequest sans ReferenceCode", "SendRequest without ReferenceCode"),
    (r"rapport jamais prêt après " + _V + r" s — dernier état", r"report never ready after \1 s — last state"),
    # ---- serveur de prix (prices_server, Worker server/prices-worker) ----
    (r"serveur injoignable", "server unreachable"),
    (r"trop d'inscriptions depuis cette adresse, réessayer dans une minute",
     "too many sign-ups from this address, try again in a minute"),
    (r"plafond d'inscriptions du jour atteint pour cette adresse",
     "daily sign-up limit reached for this address"),
    (r"plafond d'inscriptions du jour atteint, réessayer demain", "daily sign-up limit reached, try again tomorrow"),
    (r"aucune clé de cet identifiant", "no key with this identifier"),
    (r"série trop lourde", "series too large"),
    (r"instantané trop lourd", "snapshot too large"),
    (r"empreinte SHA-256 différente du contenu", "SHA-256 digest does not match the content"),
    (r"pas une série de marché", "not a market series"),
    (r"gzip attendu", "gzip expected"),
    (r"clé absente ou refusée", "key missing or refused"),
    (r"clé en lecture seule", "read-only key"),
    (r"trop de requêtes pour cette clé, ralentir", "too many requests for this key, slow down"),
    (r"route inconnue", "unknown route"),
    # ---- restes communs ----
    (r"\(trouvé: aucun\)", "(found: none)"),
    (r"\(trouvé:? ", "(found "),
    (r" doit être un objet", " must be an object"),
    (r"(^|: )critère ", r"\1criterion "),
)

_COMPILED = tuple((re.compile(pattern), repl) for pattern, repl in RULES)


def english(text: str | None) -> str | None:
    """Un message de la loi des plans, en anglais ; un message inconnu passe tel quel."""
    if not text:
        return text
    for pattern, repl in _COMPILED:
        text = pattern.sub(repl, text)
    return text
