"""Region configuration for Flemish vs Walloon specification corpora."""

from __future__ import annotations

REGIONS = frozenset({"flemish", "walloon"})

LOW_CONFIDENCE_WARNING = {
    "flemish": "Manuele check / extra foto nodig",
    "walloon": "Contrôle manuel / photo supplémentaire nécessaire",
}

LOW_CONFIDENCE_MESSAGE = {
    "flemish": "Bestekpost {nummer} ({cameras}): {warning}",
    "walloon": "Poste {nummer} ({cameras}) : {warning}",
}

CERTAINTY_LABELS = {
    "flemish": {
        "hoog": "hoog",
        "middel": "middel",
        "laag": "laag",
    },
    "walloon": {
        "hoog": "élevée",
        "middel": "moyenne",
        "laag": "faible",
    },
}

OUTPUT_STORAGE_LABELS = {
    "flemish": {
        "uploaded_images_title": "Uploaded images used for report generation",
        "before": "before",
        "after": "after",
        "options_title": "Report generation options",
        "region": "Regio",
        "report_fields": "Rapportvelden",
        "bestekpost_filter": "Bestekpost filter",
        "none_selected": "(none selected)",
        "none": "(none)",
        "camera_fallback": "Camera",
        "unknown_before": "(unknown before image)",
        "unknown_after": "(unknown after image)",
    },
    "walloon": {
        "uploaded_images_title": "Images téléchargées utilisées pour générer le rapport",
        "before": "avant",
        "after": "après",
        "options_title": "Options de génération du rapport",
        "region": "Région",
        "report_fields": "Champs du rapport",
        "bestekpost_filter": "Filtre poste CCTB",
        "none_selected": "(aucun champ sélectionné)",
        "none": "(aucun)",
        "camera_fallback": "Caméra",
        "unknown_before": "(image avant inconnue)",
        "unknown_after": "(image après inconnue)",
    },
}

KB_MESSAGES = {
    "flemish": {
        "photo_line": "Foto {idx} = {camera} {role}",
        "roles": {"voor": "voor", "na": "na"},
        "analysis_instruction": (
            "\nAnalyseer de overgang van 'voor' naar 'na' voor elke camera en geef de "
            "bestekpostnummers terug in het gevraagde JSON-formaat. "
            "Meld uitsluitend het verschil (werk uitgevoerd in deze periode), geen inventaris van de reeds bestaande staat."
        ),
        "filter_prefix": (
            "\nBeperk de output tot bestekpostnummers die binnen deze filters vallen: "
            "{filters}. Negeer waargenomen activiteit buiten deze filters."
        ),
        "agent2_intro": (
            "## Agent 1 analyse\n"
            "Hier zijn de gedetecteerde bestekposten. "
            "Zoek voor ELK nummer de details op in de knowledge base (gebruik file_search).\n"
            "Focus op bestanden die beginnen met 'Deel-X...' waar X overeenkomt met de eerste cijfers van het bestekpostnummer.\n\n"
        ),
        "agent2_active_fields_header": "## Actieve velden",
        "agent2_active_fields_body": (
            "Vul uitsluitend velden in die in het actieve JSON-schema staan.\n"
            "Actieve bestekpostvelden: {active}.\n"
            "Niet-actieve optionele velden: {inactive}.\n"
            "Als een optioneel veld niet actief is, vermeld de informatie voor dat veld nergens anders."
        ),
    },
    "walloon": {
        "photo_line": "Photo {idx} = {camera} {role}",
        "roles": {"voor": "avant", "na": "après"},
        "analysis_instruction": (
            "\nAnalysez la transition « avant » → « après » pour chaque caméra et renvoyez les "
            "postes CCTB au format JSON demandé. "
            "Ne déclarez que le delta (travaux réalisés sur la période), pas l'état déjà existant."
        ),
        "filter_prefix": (
            "\nLimitez la sortie aux postes CCTB correspondant à ces filtres : "
            "{filters}. Ignorez toute activité hors de ces filtres."
        ),
        "agent2_intro": (
            "## Analyse Agent 1\n"
            "Voici les postes CCTB détectés. "
            "Pour CHAQUE nummer, recherchez les détails dans la base (file_search).\n"
            "Ciblez les fichiers T0–T9, A (clauses administratives) ou Z selon le préfixe du poste.\n\n"
        ),
        "agent2_active_fields_header": "## Champs actifs",
        "agent2_active_fields_body": (
            "Ne remplissez que les champs présents dans le schéma JSON actif.\n"
            "Champs actifs : {active}.\n"
            "Champs optionnels inactifs : {inactive}.\n"
            "Ne reportez pas le contenu d'un champ inactif ailleurs."
        ),
    },
}

PROMPT_FILES = {
    "flemish": {"agent1": "agent1_system.txt", "agent2": "agent2_system.txt"},
    "walloon": {"agent1": "agent1_system_fr.txt", "agent2": "agent2_system_fr.txt"},
}

VECTOR_STORE_ENV_KEYS = {
    "flemish": "VECTOR_STORE_ID_FLEMISH",
    "walloon": "VECTOR_STORE_ID_WALLOON",
}

REPORT_LABELS = {
    "flemish": {
        "title": "# Vorderingsstaat – Automatisch concept",
        "subtitle": "*(Dit rapport bevat uitsluitend werk dat nieuw is uitgevoerd of gewijzigd tussen de voor- en na-foto's)*",
        "input": "## Input",
        "date_time": "- Datum/tijd: {datum}",
        "photo_pair": "- {label}: Foto {voor_idx} (voor) → Foto {na_idx} (na)",
        "overview_camera": "## Overzicht per camera",
        "no_posts": "- **{label}**: Geen bestekposten gedetecteerd",
        "camera_posts": "- **{label}**: {bps}",
        "bestekposten": "## Bestekposten",
        "post_header": "### Bestekpost {nummer} – {titel}",
        "cameras": "**Camera's:** {cameras} (Foto's: {indices})",
        "unknown": "Onbekend",
        "zekerheid": "**Zekerheid:** {zekerheid}",
        "zichtbaar": "**Uitgevoerd in deze periode**",
        "bestekeisen": "**Relevante bestekeisen / uitvoering / controle**",
        "bron": "**Bron (detailbestek)**",
        "bron_deel": "- Deel: {deel}",
        "bron_sectie": "- Sectie: {sectie}",
        "bron_fragmenten": "- Fragmenten:",
        "open_punten": "**Open punten / risico's**",
        "volgende_stap": "**Volgende stap**",
        "aandachtspunten": "## Aandachtspunten (globaal)",
        "extra_input": "## Aanbevolen extra input (indien zekerheid laag)",
    },
    "walloon": {
        "title": "# État d'avancement – Projet automatique",
        "subtitle": "*(Ce rapport ne couvre que les travaux nouveaux ou modifiés entre les photos avant et après)*",
        "input": "## Entrée",
        "date_time": "- Date/heure : {datum}",
        "photo_pair": "- {label} : Photo {voor_idx} (avant) → Photo {na_idx} (après)",
        "overview_camera": "## Vue d'ensemble par caméra",
        "no_posts": "- **{label}** : Aucun poste CCTB détecté",
        "camera_posts": "- **{label}** : {bps}",
        "bestekposten": "## Postes CCTB",
        "post_header": "### Poste {nummer} – {titel}",
        "cameras": "**Caméras :** {cameras} (Photos : {indices})",
        "unknown": "Inconnu",
        "zekerheid": "**Certitude :** {zekerheid}",
        "zichtbaar": "**Réalisé sur la période**",
        "bestekeisen": "**Exigences CCTB / exécution / contrôle**",
        "bron": "**Source (détail CCTB)**",
        "bron_deel": "- Chapitre : {deel}",
        "bron_sectie": "- Section : {sectie}",
        "bron_fragmenten": "- Extraits :",
        "open_punten": "**Points ouverts / risques**",
        "volgende_stap": "**Prochaine étape**",
        "aandachtspunten": "## Points d'attention (global)",
        "extra_input": "## Informations complémentaires recommandées (certitude faible)",
    },
}


def normalize_region(region: str) -> str:
    value = (region or "flemish").strip().lower()
    if value not in REGIONS:
        raise ValueError(f"Invalid region '{region}'. Allowed: {', '.join(sorted(REGIONS))}")
    return value
