export type Region = "flemish" | "walloon";
export type Certainty = "hoog" | "middel" | "laag" | string;
export type TrackKind = "pair" | "timelapse";
export type CompressionPreset = "low" | "medium" | "high";

export type ServerConfig = {
  max_cameras: number;
  max_image_mb: number;
  max_total_mb: number;
  video_default_frames: number;
  video_max_frames: number;
};

export type Agent1Bestekpost = {
  nummer: string;
  image_indices?: number[];
  camera_labels?: string[];
  observaties?: string[];
  zekerheid?: Certainty;
  toelichting?: string | null;
};

export type Agent1Output = {
  bestekposten: Agent1Bestekpost[];
  globale_opmerkingen?: string | null;
};

export type BronInfo = {
  deel?: string;
  sectie?: string;
  fragmenten?: string[];
  bestandsnaam?: string | null;
};

export type Agent2Bestekpost = {
  nummer: string;
  titel?: string;
  image_indices?: number[];
  camera_labels?: string[];
  zekerheid?: Certainty;
  zichtbaar_uitgevoerd?: string[];
  bestekeisen?: string[];
  bron?: BronInfo | null;
  open_punten?: string[];
  volgende_stap?: string | null;
};

export type Agent2Output = {
  bestekposten: Agent2Bestekpost[];
  aandachtspunten_globaal?: string[];
  extra_input_nodig?: string[];
};

export type EvidenceItem = {
  source_type?: "tool_call" | "annotation" | "citation" | "citation_fallback" | string;
  filename?: string | null;
  score?: number | null;
  text?: string | null;
  raw_ref?: string | null;
};

export type EvidencePayload = {
  agent1?: EvidenceItem[];
  agent2?: EvidenceItem[];
};

export type EvidenceDiagnostics = {
  agent1?: Record<string, unknown>;
  agent2?: Record<string, unknown>;
};

export type ExtractedFrame = {
  idx: number;
  timestamp_s?: number;
  data_url?: string;
};

export type ExtractedFrameGroup = {
  camera_label: string;
  frames: ExtractedFrame[];
};

export type ProgressReportResponse = {
  request_id?: string;
  markdown_report: string;
  agent1_json: Agent1Output;
  agent2_json: Agent2Output;
  evidence?: EvidencePayload;
  evidence_diagnostics?: EvidenceDiagnostics;
  extracted_frames?: ExtractedFrameGroup[];
  timings?: Record<string, number>;
  timings_display?: Record<string, string>;
};

export type StepStatus = "pending" | "running" | "done" | "error" | string;
export type JobStatus = "pending" | "running" | "complete" | "error" | string;

export type ProgressStep = {
  id: string;
  status: StepStatus;
  duration_display?: string;
  elapsed_display?: string;
};

export type ProgressJob = {
  request_id: string;
  status: JobStatus;
  steps: ProgressStep[];
  result?: ProgressReportResponse | null;
  error?: string | null;
};

export type MediaTrack =
  | {
      id: string;
      kind: "pair";
      label: string;
      before: File | null;
      after: File | null;
    }
  | {
      id: string;
      kind: "timelapse";
      label: string;
      video: File | null;
      frameCount: number;
    };

export type ReportFieldKey =
  | "zichtbaar_uitgevoerd"
  | "bestekeisen"
  | "bron"
  | "image_indices"
  | "camera_labels"
  | "open_punten"
  | "volgende_stap";

export type CompressionOptions =
  | {
      preset: CompressionPreset;
      advanced: false;
      jpegQuality: number;
      targetImageMb: number;
    }
  | {
      preset: CompressionPreset;
      advanced: true;
      jpegQuality: number;
      targetImageMb: number;
    };

export type ReportRequest = {
  tracks: MediaTrack[];
  region: Region;
  bestekpostFilter: string;
  reportFields: ReportFieldKey[];
  compression: CompressionOptions;
};

export class ApiError extends Error {
  status?: number;
  detail?: string;

  constructor(message: string, status?: number, detail?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}
