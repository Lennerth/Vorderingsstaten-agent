import { ApiError, type Region } from "../api/types";

export type Lang = "nl" | "fr";

type Key =
  | "app.title"
  | "app.subtitle"
  | "app.eyebrow"
  | "actions.generate"
  | "actions.generating"
  | "actions.addPair"
  | "actions.addTimelapse"
  | "actions.exportMd"
  | "actions.exportJson"
  | "actions.classic"
  | "sidebar.region"
  | "sidebar.regionFlemish"
  | "sidebar.regionWalloon"
  | "sidebar.filter"
  | "sidebar.fields"
  | "sidebar.processing"
  | "sidebar.compression"
  | "sidebar.compressionLow"
  | "sidebar.compressionMedium"
  | "sidebar.compressionHigh"
  | "sidebar.advanced"
  | "sidebar.quality"
  | "sidebar.target"
  | "media.title"
  | "media.before"
  | "media.after"
  | "media.video"
  | "media.frames"
  | "media.label"
  | "media.trackKind"
  | "media.pair"
  | "media.timelapse"
  | "media.dropOrClick"
  | "media.removeTrack"
  | "media.extractedFrames"
  | "pipeline.upload_validation"
  | "pipeline.video_extraction"
  | "pipeline.image_optimization"
  | "pipeline.agent1"
  | "pipeline.agent2"
  | "pipeline.report_generation"
  | "pipeline.desc.upload_validation"
  | "pipeline.desc.video_extraction"
  | "pipeline.desc.image_optimization"
  | "pipeline.desc.agent1"
  | "pipeline.desc.agent2"
  | "pipeline.desc.report_generation"
  | "report.tabReport"
  | "report.tabEvidence"
  | "report.tabMarkdown"
  | "report.tabJson"
  | "report.empty"
  | "report.emptyRunning"
  | "report.sources"
  | "report.global"
  | "report.extra"
  | "report.supporting"
  | "report.evidenceExplainer"
  | "report.noFilename"
  | "report.noSection"
  | "report.noFragment"
  | "report.noRetrievalHits"
  | "report.unknownSource"
  | "report.noSnippet"
  | "report.groupedByFile"
  | "status.request"
  | "status.loadingConfig"
  | "citation.title"
  | "citation.note"
  | "citation.clickHint"
  | "evidence.agent1"
  | "evidence.agent2"
  | "errors.title"
  | "errors.job409"
  | "errors.job400"
  | "errors.job500"
  | "errors.job404"
  | "errors.noResult"
  | "errors.pipelineFailed"
  | "a11y.headerActions"
  | "a11y.language"
  | "a11y.pipeline"
  | "a11y.reportOutput"
  | "a11y.tabs";

const dict: Record<Key, Record<Lang, string>> = {
  "app.title": { nl: "Vorderingsstaten", fr: "États d'avancement" },
  "app.subtitle": { nl: "Buildwise AI voortgangsrapport", fr: "Rapport d'avancement IA Buildwise" },
  "app.eyebrow": { nl: "Buildwise", fr: "Buildwise" },
  "actions.generate": { nl: "Rapport genereren", fr: "Générer le rapport" },
  "actions.generating": { nl: "Bezig met verwerken", fr: "Traitement en cours" },
  "actions.addPair": { nl: "voor & na foto's", fr: "photos avant & après" },
  "actions.addTimelapse": { nl: "Timelapse", fr: "Timelapse" },
  "actions.exportMd": { nl: "Markdown", fr: "Markdown" },
  "actions.exportJson": { nl: "JSON", fr: "JSON" },
  "actions.classic": { nl: "Open klassieke UI", fr: "Ouvrir l'ancienne UI" },
  "sidebar.region": { nl: "Regio", fr: "Région" },
  "sidebar.regionFlemish": { nl: "Vlaanderen", fr: "Flandre" },
  "sidebar.regionWalloon": { nl: "Wallonie", fr: "Wallonie" },
  "sidebar.filter": { nl: "Filter bestekposten", fr: "Filtre postes" },
  "sidebar.fields": { nl: "Rapportvelden", fr: "Champs du rapport" },
  "sidebar.processing": { nl: "Verwerking", fr: "Traitement" },
  "sidebar.compression": { nl: "Compressie", fr: "Compression" },
  "sidebar.compressionLow": { nl: "Laag", fr: "Faible" },
  "sidebar.compressionMedium": { nl: "Normaal", fr: "Moyen" },
  "sidebar.compressionHigh": { nl: "Hoog", fr: "Élevé" },
  "sidebar.advanced": { nl: "Geavanceerd", fr: "Avancé" },
  "sidebar.quality": { nl: "JPEG-kwaliteit", fr: "Qualité JPEG" },
  "sidebar.target": { nl: "Doelgrootte MB", fr: "Taille cible MB" },
  "media.title": { nl: "Media-invoer", fr: "Médias" },
  "media.before": { nl: "Voor", fr: "Avant" },
  "media.after": { nl: "Na", fr: "Après" },
  "media.video": { nl: "Video", fr: "Vidéo" },
  "media.frames": { nl: "Frames", fr: "Images" },
  "media.label": { nl: "Camera label", fr: "Libellé caméra" },
  "media.trackKind": { nl: "Type media", fr: "Type de média" },
  "media.pair": { nl: "voor & na foto's", fr: "photos avant & après" },
  "media.timelapse": { nl: "Timelapse", fr: "Timelapse" },
  "media.dropOrClick": { nl: "Sleep hier of klik", fr: "Glisser ici ou cliquer" },
  "media.removeTrack": { nl: "Track verwijderen", fr: "Supprimer la piste" },
  "media.extractedFrames": { nl: "Geextraheerde timelapse-frames", fr: "Images timelapse extraites" },
  "pipeline.upload_validation": { nl: "Upload validatie", fr: "Validation du téléversement" },
  "pipeline.video_extraction": { nl: "Video frame extractie", fr: "Extraction des images vidéo" },
  "pipeline.image_optimization": { nl: "Beeldoptimalisatie", fr: "Optimisation des images" },
  "pipeline.agent1": { nl: "Agent 1 - analyse", fr: "Agent 1 - analyse" },
  "pipeline.agent2": { nl: "Agent 2 - verrijking", fr: "Agent 2 - enrichissement" },
  "pipeline.report_generation": { nl: "Rapport genereren", fr: "Génération du rapport" },
  "pipeline.desc.upload_validation": {
    nl: "Controleert de uploads op formaat, aantal bestanden en basisvalidatie.",
    fr: "Contrôle les uploads : format, nombre de fichiers et validation de base.",
  },
  "pipeline.desc.video_extraction": {
    nl: "Haalt representatieve frames uit timelapse-video's.",
    fr: "Extrait des images représentatives des vidéos timelapse.",
  },
  "pipeline.desc.image_optimization": {
    nl: "Optimaliseert beelden voor snellere en stabiele analyse.",
    fr: "Optimise les images pour une analyse plus rapide et stable.",
  },
  "pipeline.desc.agent1": {
    nl: "Voert de eerste AI-analyse uit op media per camera.",
    fr: "Exécute la première analyse IA sur les médias par caméra.",
  },
  "pipeline.desc.agent2": {
    nl: "Verrijkt de analyse met context en extra controles.",
    fr: "Enrichit l'analyse avec du contexte et des contrôles supplémentaires.",
  },
  "pipeline.desc.report_generation": {
    nl: "Stelt het eindrapport samen met bevindingen en aandachtspunten.",
    fr: "Compose le rapport final avec constats et points d'attention.",
  },
  "report.tabReport": { nl: "Rapport", fr: "Rapport" },
  "report.tabEvidence": { nl: "Bewijs", fr: "Preuves" },
  "report.tabMarkdown": { nl: "Markdown", fr: "Markdown" },
  "report.tabJson": { nl: "JSON", fr: "JSON" },
  "report.empty": {
    nl: "Nog geen rapport. Voeg media toe en start de analyse.",
    fr: "Aucun rapport. Ajoutez des médias et lancez l'analyse.",
  },
  "report.emptyRunning": { nl: "Bezig", fr: "En cours" },
  "report.sources": { nl: "Bronnen", fr: "Sources" },
  "report.global": { nl: "Globale aandachtspunten", fr: "Points d'attention globaux" },
  "report.extra": { nl: "Extra input nodig", fr: "Entrée supplémentaire requise" },
  "report.supporting": { nl: "Ondersteunende retrievalcontext", fr: "Contexte de recherche complémentaire" },
  "report.evidenceExplainer": {
    nl: "Per-post bronvelden zijn de sterkste herleidbaarheid. De retrievalhits hieronder zijn globale ondersteunende context en geen perfecte koppeling per post.",
    fr: "Les champs source par poste offrent la meilleure traçabilité. Les hits de retrieval ci-dessous sont un contexte global de soutien, pas un lien déterministe par poste.",
  },
  "report.noFilename": { nl: "Geen bestandsnaam", fr: "Pas de nom de fichier" },
  "report.noSection": { nl: "Geen sectie", fr: "Pas de section" },
  "report.noFragment": { nl: "Geen bronfragment voor deze post.", fr: "Aucun fragment source pour ce poste." },
  "report.noRetrievalHits": { nl: "Geen retrievalhits teruggegeven.", fr: "Aucun hit de retrieval retourné." },
  "report.unknownSource": { nl: "Onbekende bron", fr: "Source inconnue" },
  "report.noSnippet": { nl: "Geen snippet-tekst teruggegeven.", fr: "Aucun texte de snippet retourné." },
  "report.groupedByFile": { nl: "Gegroepeerd per bestand", fr: "Groupe par fichier" },
  "status.request": { nl: "Aanvraag", fr: "Requête" },
  "status.loadingConfig": { nl: "Backendconfiguratie laden...", fr: "Chargement de la configuration backend..." },
  "citation.title": { nl: "Broncontext", fr: "Contexte source" },
  "citation.note": {
    nl: "Betrouwbare per-post bron. Geen gegarandeerde koppeling met globale retrievalhits.",
    fr: "Source fiable par poste. Pas de lien garanti avec les hits de retrieval globaux.",
  },
  "citation.clickHint": {
    nl: "Klik voor broninformatie",
    fr: "Cliquer pour plus d'informations",
  },
  "evidence.agent1": { nl: "Agent 1", fr: "Agent 1" },
  "evidence.agent2": { nl: "Agent 2", fr: "Agent 2" },
  "errors.title": { nl: "Er ging iets mis", fr: "Une erreur est survenue" },
  "errors.job409": {
    nl: "Er loopt al een ander rapport. Wacht tot het klaar is en probeer opnieuw.",
    fr: "Un autre rapport est déjà en cours. Attendez la fin puis réessayez.",
  },
  "errors.job400": { nl: "Validatiefout", fr: "Erreur de validation" },
  "errors.job500": { nl: "Pipelinefout", fr: "Erreur pipeline" },
  "errors.job404": {
    nl: "Voortgangsjob niet gevonden. Mogelijk verlopen of backend herstart.",
    fr: "Job de progression introuvable. Peut-être expiré ou backend redémarré.",
  },
  "errors.noResult": { nl: "Job voltooid maar zonder resultaat.", fr: "Job terminé sans résultat." },
  "errors.pipelineFailed": { nl: "Pipeline mislukt.", fr: "Échec du pipeline." },
  "a11y.headerActions": { nl: "Kopacties", fr: "Actions en-tête" },
  "a11y.language": { nl: "Taal", fr: "Langue" },
  "a11y.pipeline": { nl: "Pipelinestatus", fr: "Statut pipeline" },
  "a11y.reportOutput": { nl: "Rapportuitvoer", fr: "Sortie rapport" },
  "a11y.tabs": { nl: "Rapporttabs", fr: "Onglets rapport" },
};

export function t(lang: Lang, key: Key): string {
  return dict[key][lang];
}

export function suggestedLang(region: Region): Lang {
  return region === "walloon" ? "fr" : "nl";
}

export function fieldLabel(lang: Lang, field: string): string {
  const labels: Record<string, Record<Lang, string>> = {
    zichtbaar_uitgevoerd: { nl: "Uitgevoerd", fr: "Exécuté" },
    bestekeisen: { nl: "Bestekeisen", fr: "Exigences" },
    bron: { nl: "Bron", fr: "Source" },
    image_indices: { nl: "Foto-indexen", fr: "Index photos" },
    camera_labels: { nl: "Camera's", fr: "Caméras" },
    open_punten: { nl: "Open punten", fr: "Points ouverts" },
    volgende_stap: { nl: "Volgende stap", fr: "Étape suivante" },
  };
  return labels[field]?.[lang] ?? field;
}

const CERTAINTY_LABELS: Record<string, Record<Lang, string>> = {
  hoog: { nl: "hoog", fr: "élevée" },
  middel: { nl: "middel", fr: "moyenne" },
  laag: { nl: "laag", fr: "faible" },
};

const SOURCE_TYPE_LABELS: Record<string, Record<Lang, string>> = {
  unknown: { nl: "onbekend", fr: "inconnu" },
  tool_call: { nl: "tool-aanroep", fr: "appel d'outil" },
  annotation: { nl: "annotatie", fr: "annotation" },
  citation: { nl: "citatie", fr: "citation" },
  citation_fallback: { nl: "citatie (fallback)", fr: "citation (secours)" },
};

const JOB_STATUS_LABELS: Record<string, Record<Lang, string>> = {
  pending: { nl: "wachten", fr: "en attente" },
  running: { nl: "bezig", fr: "en cours" },
  complete: { nl: "voltooid", fr: "terminé" },
  error: { nl: "fout", fr: "erreur" },
};

const STEP_STATUS_LABELS: Record<string, Record<Lang, string>> = {
  pending: { nl: "wachten", fr: "en attente" },
  running: { nl: "bezig", fr: "en cours" },
  done: { nl: "klaar", fr: "terminé" },
  error: { nl: "fout", fr: "erreur" },
};

export function certaintyLabel(lang: Lang, value: string | undefined): string {
  const key = (value ?? "laag").toLowerCase();
  return CERTAINTY_LABELS[key]?.[lang] ?? value ?? "?";
}

/** Raw certainty value for CSS badge classes (hoog/middel/laag). */
export function certaintyClass(value: string | undefined): string {
  const key = (value ?? "laag").toLowerCase();
  return CERTAINTY_LABELS[key] ? key : "laag";
}

export function sourceTypeLabel(lang: Lang, value: string | undefined): string {
  const key = (value ?? "unknown").trim().toLowerCase();
  return SOURCE_TYPE_LABELS[key]?.[lang] ?? value ?? SOURCE_TYPE_LABELS.unknown[lang];
}

export function evidenceFilenameLabel(lang: Lang, filename: string): string {
  const key = filename.trim().toLowerCase();
  if (key === "unknown") return SOURCE_TYPE_LABELS.unknown[lang];
  return filename;
}

export function jobStatusLabel(lang: Lang, status: string | undefined): string {
  const key = (status ?? "pending").toLowerCase();
  return JOB_STATUS_LABELS[key]?.[lang] ?? status ?? key;
}

export function stepStatusLabel(lang: Lang, status: string | undefined): string {
  const key = (status ?? "pending").toLowerCase();
  return STEP_STATUS_LABELS[key]?.[lang] ?? status ?? key;
}

export function normalizeError(lang: Lang, error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409) return t(lang, "errors.job409");
    if (error.status === 400) return `${t(lang, "errors.job400")}: ${error.detail || error.message}`;
    if (error.status === 500) return `${t(lang, "errors.job500")}: ${error.detail || error.message}`;
    if (error.status === 404) return t(lang, "errors.job404");
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return String(error);
}
