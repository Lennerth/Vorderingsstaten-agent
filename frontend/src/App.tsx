import { useEffect, useMemo, useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";
import {
  AlertTriangle,
  Camera,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Database,
  FileJson,
  FileText,
  ImageIcon,
  Loader2,
  Plus,
  Search,
  Trash2,
  Video,
} from "lucide-react";
import { ApiError, type CompressionOptions, type MediaTrack, type ProgressJob, type ProgressReportResponse, type Region, type ReportFieldKey, type ServerConfig } from "./api/types";
import { fetchConfig, fetchProgress, startProgressReportJob } from "./api/client";
import { CitationPopover } from "./components/CitationPopover";
import { exportJson, exportMarkdown } from "./lib/export";
import { getClassicUiUrl } from "./lib/classicUiUrl";
import { groupEvidenceByFileAndType } from "./lib/groupEvidence";
import buildwiseLogo from "./assets/buildwise-logo.png";
import {
  certaintyClass,
  certaintyLabel,
  evidenceFilenameLabel,
  fieldLabel,
  jobStatusLabel,
  normalizeError,
  sourceTypeLabel,
  suggestedLang,
  t,
  type Lang,
} from "./lib/i18n";

const reportFields: ReportFieldKey[] = [
  "zichtbaar_uitgevoerd",
  "bestekeisen",
  "bron",
  "image_indices",
  "camera_labels",
  "open_punten",
  "volgende_stap",
];

const stepIds = [
  "upload_validation",
  "video_extraction",
  "image_optimization",
  "agent1",
  "agent2",
  "report_generation",
];

function newPair(index: number): MediaTrack {
  return {
    id: crypto.randomUUID(),
    kind: "pair",
    label: `Camera ${index + 1}`,
    before: null,
    after: null,
  };
}

function newTimelapse(index: number, frameCount: number): MediaTrack {
  return {
    id: crypto.randomUUID(),
    kind: "timelapse",
    label: `Timelapse ${index + 1}`,
    video: null,
    frameCount,
  };
}

function switchTrackKind(track: MediaTrack, kind: MediaTrack["kind"], defaultFrames: number): MediaTrack {
  if (track.kind === kind) return track;
  if (kind === "pair") {
    return { id: track.id, kind: "pair", label: track.label, before: null, after: null };
  }
  return { id: track.id, kind: "timelapse", label: track.label, video: null, frameCount: defaultFrames };
}

function defaultFields(): Record<ReportFieldKey, boolean> {
  return Object.fromEntries(reportFields.map((field) => [field, true])) as Record<ReportFieldKey, boolean>;
}

function App() {
  const [region, setRegion] = useState<Region>(() => (navigator.language.startsWith("fr") ? "walloon" : "flemish"));
  const lang = suggestedLang(region);
  const [tracks, setTracks] = useState<MediaTrack[]>(() => [newPair(0)]);
  const [bestekpostFilter, setBestekpostFilter] = useState("");
  const [fields, setFields] = useState<Record<ReportFieldKey, boolean>>(() => defaultFields());
  const [compression, setCompression] = useState<CompressionOptions>({
    preset: "medium",
    advanced: false,
    jpegQuality: 80,
    targetImageMb: 2,
  });
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [job, setJob] = useState<ProgressJob | null>(null);
  const [data, setData] = useState<ProgressReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  useEffect(() => {
    const raw = localStorage.getItem("v2-ui-settings");
    if (!raw) return;
    try {
      const saved = JSON.parse(raw) as {
        region?: Region;
        bestekpostFilter?: string;
        fields?: Record<ReportFieldKey, boolean>;
        compression?: CompressionOptions;
      };
      if (saved.region === "flemish" || saved.region === "walloon") setRegion(saved.region);
      if (typeof saved.bestekpostFilter === "string") setBestekpostFilter(saved.bestekpostFilter);
      if (saved.fields) setFields({ ...defaultFields(), ...saved.fields });
      if (saved.compression) setCompression(saved.compression);
    } catch {
      localStorage.removeItem("v2-ui-settings");
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(
      "v2-ui-settings",
      JSON.stringify({ region, bestekpostFilter, fields, compression }),
    );
  }, [region, bestekpostFilter, fields, compression]);

  useEffect(() => {
    fetchConfig()
      .then(setConfig)
      .catch((err: unknown) => setError(normalizeError(lang, err)));
  }, []);

  const canGenerate = useMemo(
    () =>
      tracks.length > 0 &&
      tracks.every((track) =>
        track.kind === "pair" ? Boolean(track.before && track.after) : Boolean(track.video),
      ),
    [tracks],
  );

  const selectedFields = useMemo(
    () => reportFields.filter((field) => fields[field]),
    [fields],
  );

  async function runReport() {
    setError(null);
    setData(null);
    setJob(null);
    setLoading(true);
    try {
      const started = await startProgressReportJob({
        tracks,
        region,
        bestekpostFilter,
        reportFields: selectedFields,
        compression,
      });
      await pollUntilDone(started.request_id);
    } catch (err) {
      setError(normalizeError(lang, err));
    } finally {
      setLoading(false);
    }
  }

  async function pollUntilDone(requestId: string) {
    let misses = 0;
    for (;;) {
      await delay(misses ? 1800 : 900);
      let next: ProgressJob;
      try {
        next = await fetchProgress(requestId);
      } catch (err) {
        misses += 1;
        if (err instanceof ApiError && err.status === 404) {
          throw new ApiError(t(lang, "errors.job404"), 404);
        }
        if (misses >= 4) throw err;
        continue;
      }
      misses = 0;
      setJob(next);
      if (next.status === "complete") {
        if (!next.result) throw new ApiError(t(lang, "errors.noResult"));
        setData(next.result);
        return;
      }
      if (next.status === "error") {
        throw new ApiError(next.error || t(lang, "errors.pipelineFailed"));
      }
    }
  }

  function updateTrack(id: string, next: MediaTrack) {
    setTracks((current) => current.map((track) => (track.id === id ? next : track)));
  }

  function removeTrack(id: string) {
    setTracks((current) => (current.length > 1 ? current.filter((track) => track.id !== id) : current));
  }

  function chooseRegion(next: Region) {
    setRegion(next);
  }

  const maxCameras = config?.max_cameras ?? 6;
  const canAddTrack = tracks.length < maxCameras;

  return (
    <div className="app-shell">
      <Sidebar
        lang={lang}
        region={region}
        onRegion={chooseRegion}
        bestekpostFilter={bestekpostFilter}
        setBestekpostFilter={setBestekpostFilter}
        fields={fields}
        setFields={setFields}
        compression={compression}
        setCompression={setCompression}
        loading={loading}
        canGenerate={canGenerate}
        onGenerate={runReport}
      />

      <main className="workspace">
        <Header
          lang={lang}
          data={data}
          loading={loading}
          onExportMd={() => exportMarkdown(data?.markdown_report ?? "")}
          onExportJson={() => exportJson(data)}
        />
        <PipelineStepper lang={lang} job={job} loading={loading} />
        <StatusBar lang={lang} job={job} error={error} config={config} />

        <div className="content-grid">
          <section className="media-column" aria-label={t(lang, "media.title")}>
            <div className="section-heading">
              <span>{t(lang, "media.title")}</span>
              <div className="heading-actions">
                <button
                  className="button secondary small"
                  type="button"
                  disabled={!canAddTrack}
                  onClick={() => setTracks((current) => [...current, newPair(current.length)])}
                >
                  <Plus size={14} /> {t(lang, "actions.addPair")}
                </button>
                <button
                  className="button secondary small"
                  type="button"
                  disabled={!canAddTrack}
                  onClick={() =>
                    setTracks((current) => [
                      ...current,
                      newTimelapse(current.length, config?.video_default_frames ?? 8),
                    ])
                  }
                >
                  <Video size={14} /> {t(lang, "actions.addTimelapse")}
                </button>
              </div>
            </div>
            <div className="track-list">
              {tracks.map((track, index) => (
                <TrackCard
                  key={track.id}
                  lang={lang}
                  track={track}
                  index={index}
                  config={config}
                  onChange={(next) => updateTrack(track.id, next)}
                  onRemove={() => removeTrack(track.id)}
                  canRemove={tracks.length > 1}
                />
              ))}
            </div>
            <ExtractedFrames lang={lang} frames={data?.extracted_frames ?? []} />
          </section>

          <ReportPanel lang={lang} data={data} loading={loading} job={job} />
        </div>
      </main>
    </div>
  );
}

type SidebarProps = {
  lang: Lang;
  region: Region;
  onRegion: (region: Region) => void;
  bestekpostFilter: string;
  setBestekpostFilter: (value: string) => void;
  fields: Record<ReportFieldKey, boolean>;
  setFields: (value: Record<ReportFieldKey, boolean>) => void;
  compression: CompressionOptions;
  setCompression: (value: CompressionOptions) => void;
  loading: boolean;
  canGenerate: boolean;
  onGenerate: () => void;
};

function Sidebar(props: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <img className="brand-logo" src={buildwiseLogo} alt="" />
        <div>
          <h1>{t(props.lang, "app.title")}</h1>
          <p>{t(props.lang, "app.subtitle")}</p>
        </div>
      </div>

      <section className="sidebar-section">
        <label className="label">{t(props.lang, "sidebar.region")}</label>
        <div className="segmented" role="group" aria-label={t(props.lang, "sidebar.region")}>
          <button
            type="button"
            className={props.region === "flemish" ? "active" : ""}
            onClick={() => props.onRegion("flemish")}
          >
            {t(props.lang, "sidebar.regionFlemish")}
          </button>
          <button
            type="button"
            className={props.region === "walloon" ? "active" : ""}
            onClick={() => props.onRegion("walloon")}
          >
            {t(props.lang, "sidebar.regionWalloon")}
          </button>
        </div>
      </section>

      <section className="sidebar-section">
        <label className="label" htmlFor="bestekpost-filter">
          {t(props.lang, "sidebar.filter")}
        </label>
        <input
          id="bestekpost-filter"
          className="input"
          value={props.bestekpostFilter}
          placeholder="02, 10.00, 13.10"
          onChange={(event) => props.setBestekpostFilter(event.target.value)}
        />
      </section>

      <section className="sidebar-section fields-section">
        <h2>{t(props.lang, "sidebar.fields")}</h2>
        <div className="check-list">
          {reportFields.map((field) => (
            <label key={field} className="check-row">
              <input
                type="checkbox"
                checked={props.fields[field]}
                onChange={(event) => props.setFields({ ...props.fields, [field]: event.target.checked })}
              />
              <span>{fieldLabel(props.lang, field)}</span>
            </label>
          ))}
        </div>
      </section>

      <details className="sidebar-section details" open>
        <summary>
          <span>{t(props.lang, "sidebar.processing")}</span>
          <ChevronDown size={14} />
        </summary>
        <label className="label" htmlFor="compression-preset">
          {t(props.lang, "sidebar.compression")}
        </label>
        <select
          id="compression-preset"
          className="input"
          value={props.compression.preset}
          onChange={(event) => props.setCompression({ ...props.compression, preset: event.target.value as CompressionOptions["preset"] })}
        >
          <option value="low">{t(props.lang, "sidebar.compressionLow")}</option>
          <option value="medium">{t(props.lang, "sidebar.compressionMedium")}</option>
          <option value="high">{t(props.lang, "sidebar.compressionHigh")}</option>
        </select>
        <label className="check-row">
          <input
            type="checkbox"
            checked={props.compression.advanced}
            onChange={(event) => props.setCompression({ ...props.compression, advanced: event.target.checked } as CompressionOptions)}
          />
          <span>{t(props.lang, "sidebar.advanced")}</span>
        </label>
        {props.compression.advanced ? (
          <div className="two-columns">
            <label>
              <span className="label">{t(props.lang, "sidebar.quality")}</span>
              <input
                className="input"
                type="number"
                min={1}
                max={95}
                value={props.compression.jpegQuality}
                onChange={(event) =>
                  props.setCompression({ ...props.compression, jpegQuality: Number(event.target.value) })
                }
              />
            </label>
            <label>
              <span className="label">{t(props.lang, "sidebar.target")}</span>
              <input
                className="input"
                type="number"
                min={0.2}
                max={10}
                step={0.1}
                value={props.compression.targetImageMb}
                onChange={(event) =>
                  props.setCompression({ ...props.compression, targetImageMb: Number(event.target.value) })
                }
              />
            </label>
          </div>
        ) : null}
      </details>

      <button className="button primary generate" disabled={props.loading || !props.canGenerate} onClick={props.onGenerate}>
        {props.loading ? <Loader2 className="spin" size={18} /> : <Search size={18} />}
        {props.loading ? t(props.lang, "actions.generating") : t(props.lang, "actions.generate")}
      </button>
    </aside>
  );
}

function Header({
  lang,
  data,
  loading,
  onExportMd,
  onExportJson,
}: {
  lang: Lang;
  data: ProgressReportResponse | null;
  loading: boolean;
  onExportMd: () => void;
  onExportJson: () => void;
}) {
  return (
    <header className="topbar">
      <div>
        <span className="eyebrow">{t(lang, "app.eyebrow")}</span>
        <strong>{t(lang, "app.subtitle")}</strong>
      </div>
      <nav className="top-actions" aria-label={t(lang, "a11y.headerActions")}>
        <a className="button ghost" href={getClassicUiUrl()} target="_blank" rel="noreferrer">
          {t(lang, "actions.classic")}
        </a>
        <span className="locale-pill" aria-label={t(lang, "a11y.language")}>
          {lang.toUpperCase()}
        </span>
        <button className="button secondary" disabled={!data || loading} onClick={onExportMd}>
          <FileText size={15} /> {t(lang, "actions.exportMd")}
        </button>
        <button className="button secondary" disabled={!data || loading} onClick={onExportJson}>
          <FileJson size={15} /> {t(lang, "actions.exportJson")}
        </button>
      </nav>
    </header>
  );
}

function PipelineStepper({ lang, job, loading }: { lang: Lang; job: ProgressJob | null; loading: boolean }) {
  const steps = stepIds.map((id) => job?.steps.find((step) => step.id === id) ?? { id, status: "pending" });
  return (
    <div className="stepper" aria-label={t(lang, "a11y.pipeline")}>
      {steps.map((step) => (
        <div
          key={step.id}
          className={`step ${step.status}`}
          title={t(lang, `pipeline.desc.${step.id}` as Parameters<typeof t>[1])}
        >
          <span className="step-icon">{step.status === "done" ? <CheckCircle2 size={14} /> : loading && step.status === "running" ? <Loader2 className="spin" size={14} /> : <Clock3 size={14} />}</span>
          <span>{t(lang, `pipeline.${step.id}` as Parameters<typeof t>[1])}</span>
          {step.duration_display ? <small>{step.duration_display}</small> : null}
        </div>
      ))}
    </div>
  );
}

function StatusBar({
  lang,
  job,
  error,
  config,
}: {
  lang: Lang;
  job: ProgressJob | null;
  error: string | null;
  config: ServerConfig | null;
}) {
  if (error) {
    return (
      <div className="status error" role="alert">
        <AlertTriangle size={16} />
        <div>
          <strong>{t(lang, "errors.title")}</strong>
          <p>{error}</p>
        </div>
      </div>
    );
  }
  if (job) {
    return (
      <div className="status info">
        <Database size={16} />
        <span>
          {t(lang, "status.request")} <code>{job.request_id}</code> · {jobStatusLabel(lang, job.status)}
        </span>
      </div>
    );
  }
  if (!config) {
    return (
      <div className="status info">
        <Loader2 className="spin" size={16} />
        <span>{t(lang, "status.loadingConfig")}</span>
      </div>
    );
  }
  return null;
}

function TrackCard({
  lang,
  track,
  index,
  config,
  onChange,
  onRemove,
  canRemove,
}: {
  lang: Lang;
  track: MediaTrack;
  index: number;
  config: ServerConfig | null;
  onChange: (track: MediaTrack) => void;
  onRemove: () => void;
  canRemove: boolean;
}) {
  return (
    <article className="track-card">
      <header>
        <div className="track-title">
          {track.kind === "pair" ? <Camera size={17} /> : <Video size={17} />}
          <div>
            <strong>{track.label.trim() || `Camera ${index + 1}`}</strong>
            <span className="mono">CAM_{String(index + 1).padStart(2, "0")}</span>
          </div>
        </div>
        <button
          className="icon-button"
          type="button"
          disabled={!canRemove}
          onClick={onRemove}
          aria-label={t(lang, "media.removeTrack")}
        >
          <Trash2 size={16} />
        </button>
      </header>
      <label className="label" htmlFor={`${track.id}-label`}>
        {t(lang, "media.label")}
      </label>
      <input
        id={`${track.id}-label`}
        className="input"
        value={track.label}
        onChange={(event) => onChange({ ...track, label: event.target.value })}
      />
      <div className="segmented track-kind" role="group" aria-label={t(lang, "media.trackKind")}>
        <button
          type="button"
          className={track.kind === "pair" ? "active" : ""}
          onClick={() =>
            onChange(switchTrackKind(track, "pair", config?.video_default_frames ?? 8))
          }
        >
          {t(lang, "media.pair")}
        </button>
        <button
          type="button"
          className={track.kind === "timelapse" ? "active" : ""}
          onClick={() =>
            onChange(switchTrackKind(track, "timelapse", config?.video_default_frames ?? 8))
          }
        >
          {t(lang, "media.timelapse")}
        </button>
      </div>
      {track.kind === "pair" ? (
        <div className="media-slots">
          <FileSlot
            lang={lang}
            label={t(lang, "media.before")}
            accept="image/*"
            file={track.before}
            onFile={(file) => onChange({ ...track, before: file })}
          />
          <FileSlot
            lang={lang}
            label={t(lang, "media.after")}
            accept="image/*"
            file={track.after}
            onFile={(file) => onChange({ ...track, after: file })}
          />
        </div>
      ) : (
        <div className="video-track">
          <FileSlot
            lang={lang}
            label={t(lang, "media.video")}
            accept="video/mp4,video/quicktime,video/*"
            file={track.video}
            onFile={(file) => onChange({ ...track, video: file })}
          />
          <label>
            <span className="label">{t(lang, "media.frames")}</span>
            <input
              className="input"
              type="number"
              min={2}
              max={config?.video_max_frames ?? 16}
              value={track.frameCount}
              onChange={(event) => onChange({ ...track, frameCount: Number(event.target.value) })}
            />
          </label>
        </div>
      )}
    </article>
  );
}

function FileSlot({
  lang,
  label,
  accept,
  file,
  onFile,
}: {
  lang: Lang;
  label: string;
  accept: string;
  file: File | null;
  onFile: (file: File | null) => void;
}) {
  const [preview, setPreview] = useState<string | null>(null);
  useEffect(() => {
    if (!file || !file.type.startsWith("image/")) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function onChange(event: ChangeEvent<HTMLInputElement>) {
    onFile(event.target.files?.[0] ?? null);
  }

  return (
    <label className={`file-slot${preview ? " has-preview" : ""}`}>
      <span className="label">{label}</span>
      <input type="file" accept={accept} onChange={onChange} />
      {preview ? (
        <div className="file-slot-preview">
          <img src={preview} alt="" />
        </div>
      ) : (
        <ImageIcon size={30} />
      )}
      <strong>{file?.name ?? t(lang, "media.dropOrClick")}</strong>
      {file ? <small>{formatBytes(file.size)}</small> : null}
    </label>
  );
}

function ExtractedFrames({
  lang,
  frames,
}: {
  lang: Lang;
  frames: NonNullable<ProgressReportResponse["extracted_frames"]>;
}) {
  if (!frames.length) return null;
  return (
    <section className="extracted-frames">
      <h3>{t(lang, "media.extractedFrames")}</h3>
      {frames.map((group) => (
        <div key={group.camera_label}>
          <strong>{group.camera_label}</strong>
          <div className="frame-strip">
            {group.frames.map((frame) => (
              <figure key={frame.idx}>
                {frame.data_url ? <img src={frame.data_url} alt={`${group.camera_label} frame ${frame.idx}`} /> : null}
                <figcaption>#{frame.idx} {typeof frame.timestamp_s === "number" ? `${frame.timestamp_s.toFixed(1)}s` : ""}</figcaption>
              </figure>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}

type ReportTabId = "report" | "evidence" | "markdown" | "json";

function ReportPanel({
  lang,
  data,
  loading,
  job,
}: {
  lang: Lang;
  data: ProgressReportResponse | null;
  loading: boolean;
  job: ProgressJob | null;
}) {
  const [tab, setTab] = useState<ReportTabId>("report");
  const tablistRef = useRef<HTMLDivElement>(null);
  const tabs: { id: ReportTabId; label: string }[] = [
    { id: "report", label: t(lang, "report.tabReport") },
    { id: "evidence", label: t(lang, "report.tabEvidence") },
    { id: "markdown", label: t(lang, "report.tabMarkdown") },
    { id: "json", label: t(lang, "report.tabJson") },
  ];

  function onTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const nextIndex =
      event.key === "ArrowRight"
        ? (index + 1) % tabs.length
        : (index - 1 + tabs.length) % tabs.length;
    const nextId = tabs[nextIndex].id;
    setTab(nextId);
    const buttons = tablistRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    buttons?.[nextIndex]?.focus();
  }

  return (
    <section className="report-panel" aria-label={t(lang, "a11y.reportOutput")}>
      <div className="tabs" role="tablist" aria-label={t(lang, "a11y.tabs")} ref={tablistRef}>
        {tabs.map(({ id, label }, index) => (
          <button
            key={id}
            id={`tab-${id}`}
            className={tab === id ? "active" : ""}
            onClick={() => setTab(id)}
            onKeyDown={(event) => onTabKeyDown(event, index)}
            role="tab"
            type="button"
            aria-selected={tab === id}
            aria-controls={`panel-${id}`}
            tabIndex={tab === id ? 0 : -1}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="report-body">
        {!data ? <EmptyReport lang={lang} loading={loading} job={job} /> : null}
        {data ? (
          <>
            <div
              id="panel-report"
              role="tabpanel"
              aria-labelledby="tab-report"
              hidden={tab !== "report"}
              className={tab === "report" ? "" : "tabpanel-hidden"}
            >
              {tab === "report" ? <StructuredReport lang={lang} data={data} /> : null}
            </div>
            <div
              id="panel-evidence"
              role="tabpanel"
              aria-labelledby="tab-evidence"
              hidden={tab !== "evidence"}
              className={tab === "evidence" ? "" : "tabpanel-hidden"}
            >
              {tab === "evidence" ? <EvidenceTab lang={lang} data={data} /> : null}
            </div>
            <div
              id="panel-markdown"
              role="tabpanel"
              aria-labelledby="tab-markdown"
              hidden={tab !== "markdown"}
              className={tab === "markdown" ? "" : "tabpanel-hidden"}
            >
              {tab === "markdown" ? <pre className="markdown-view">{data.markdown_report}</pre> : null}
            </div>
            <div
              id="panel-json"
              role="tabpanel"
              aria-labelledby="tab-json"
              hidden={tab !== "json"}
              className={tab === "json" ? "" : "tabpanel-hidden"}
            >
              {tab === "json" ? <JsonBlock value={data} /> : null}
            </div>
          </>
        ) : null}
      </div>
    </section>
  );
}

function EmptyReport({ lang, loading, job }: { lang: Lang; loading: boolean; job: ProgressJob | null }) {
  return (
    <div className="empty-state">
      {loading ? <Loader2 className="spin" size={34} /> : <FileText size={34} />}
      <p>
        {loading && job
          ? `${jobStatusLabel(lang, job.status)} (${t(lang, "report.emptyRunning")})...`
          : t(lang, "report.empty")}
      </p>
    </div>
  );
}

function StructuredReport({ lang, data }: { lang: Lang; data: ProgressReportResponse }) {
  const posts = data.agent2_json?.bestekposten ?? [];
  return (
    <div className="report-stack">
      {posts.map((post) => (
        <BestekpostCard key={post.nummer} post={post} lang={lang} />
      ))}
      <NoticeList title={t(lang, "report.global")} items={data.agent2_json.aandachtspunten_globaal ?? []} tone="blue" />
      <NoticeList title={t(lang, "report.extra")} items={data.agent2_json.extra_input_nodig ?? []} tone="green" />
    </div>
  );
}

function BestekpostCard({ post, lang }: { post: ProgressReportResponse["agent2_json"]["bestekposten"][number]; lang: Lang }) {
  const confidence = certaintyClass(post.zekerheid);
  return (
    <article className="bestek-card">
      <header>
        <div>
          <span className="post-number">{post.nummer}</span>
          <h3>{post.titel ?? post.nummer}</h3>
        </div>
        <span className={`badge ${confidence}`}>{certaintyLabel(lang, post.zekerheid)}</span>
      </header>
      <div className="proof-ribbon">
        {(post.camera_labels ?? []).map((camera) => <span key={camera}><Camera size={12} />{camera}</span>)}
        {(post.image_indices ?? []).length ? <span><ImageIcon size={12} />#{post.image_indices?.join(", #")}</span> : null}
        {post.bron?.bestandsnaam ? <span><FileText size={12} />{post.bron.bestandsnaam}</span> : null}
        {post.bron?.sectie ? <span>{post.bron.sectie}</span> : null}
      </div>
      <CardSection
        lang={lang}
        post={post}
        title={fieldLabel(lang, "zichtbaar_uitgevoerd")}
        items={post.zichtbaar_uitgevoerd ?? []}
      />
      <CardSection lang={lang} post={post} title={fieldLabel(lang, "bestekeisen")} items={post.bestekeisen ?? []} muted />
      {post.bron?.fragmenten?.length ? (
        <details className="source-box">
          <summary>{t(lang, "report.sources")} · {post.bron.deel ?? ""}</summary>
          {post.bron.fragmenten.map((fragment, index) => (
            <CitationPopover key={`${post.nummer}-${index}`} lang={lang} post={post} fragment={fragment}>
              <blockquote>{fragment}</blockquote>
            </CitationPopover>
          ))}
        </details>
      ) : null}
      <CardSection
        lang={lang}
        post={post}
        title={fieldLabel(lang, "open_punten")}
        items={post.open_punten ?? []}
        warning
      />
      {post.volgende_stap ? (
        <div className="next-step">
          <strong>{fieldLabel(lang, "volgende_stap")}</strong>
          <p>{post.volgende_stap}</p>
        </div>
      ) : null}
    </article>
  );
}

function CardSection({
  lang,
  post,
  title,
  items,
  muted,
  warning,
}: {
  lang: Lang;
  post: ProgressReportResponse["agent2_json"]["bestekposten"][number];
  title: string;
  items: string[];
  muted?: boolean;
  warning?: boolean;
}) {
  if (!items.length) return null;
  const useCitation = title === fieldLabel(lang, "zichtbaar_uitgevoerd");
  return (
    <section className={warning ? "card-section warning" : muted ? "card-section muted" : "card-section"}>
      <h4>{title}</h4>
      <ul>
        {items.map((item, index) => (
          <li key={`${title}-${index}`}>
            {useCitation ? (
              <CitationPopover lang={lang} post={post}>
                <span>{item}</span>
              </CitationPopover>
            ) : (
              item
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function NoticeList({ title, items, tone }: { title: string; items: string[]; tone: "blue" | "green" }) {
  if (!items.length) return null;
  return (
    <section className={`notice-list ${tone}`}>
      <h3>{title}</h3>
      <ul>
        {items.map((item, index) => <li key={`${title}-${index}`}>{item}</li>)}
      </ul>
    </section>
  );
}

function EvidenceTab({ lang, data }: { lang: Lang; data: ProgressReportResponse }) {
  const agent1 = data.evidence?.agent1 ?? [];
  const agent2 = data.evidence?.agent2 ?? [];
  const agent1Groups = groupEvidenceByFileAndType(agent1);
  const agent2Groups = groupEvidenceByFileAndType(agent2);

  return (
    <div className="evidence-view">
      <section className="evidence-explainer">
        <AlertTriangle size={17} />
        <p>{t(lang, "report.evidenceExplainer")}</p>
      </section>
      <h3>{t(lang, "report.sources")}</h3>
      <SourceSummary lang={lang} data={data} />
      <GroupedEvidenceSection
        lang={lang}
        agentLabel={t(lang, "evidence.agent1")}
        groups={agent1Groups}
        totalCount={agent1.length}
      />
      <GroupedEvidenceSection
        lang={lang}
        agentLabel={t(lang, "evidence.agent2")}
        groups={agent2Groups}
        totalCount={agent2.length}
      />
      <JsonBlock value={data.evidence_diagnostics ?? {}} title="evidence_diagnostics" />
    </div>
  );
}

function SourceSummary({ lang, data }: { lang: Lang; data: ProgressReportResponse }) {
  const posts = data.agent2_json.bestekposten ?? [];
  return (
    <div className="source-grid">
      {posts.map((post) => (
        <article key={post.nummer}>
          <span className="post-number">{post.nummer}</span>
          <strong>{post.bron?.bestandsnaam ?? t(lang, "report.noFilename")}</strong>
          <small>{post.bron?.sectie ?? t(lang, "report.noSection")}</small>
          <p>{post.bron?.fragmenten?.[0] ?? t(lang, "report.noFragment")}</p>
        </article>
      ))}
    </div>
  );
}

function GroupedEvidenceSection({
  lang,
  agentLabel,
  groups,
  totalCount,
}: {
  lang: Lang;
  agentLabel: string;
  groups: ReturnType<typeof groupEvidenceByFileAndType>;
  totalCount: number;
}) {
  return (
    <details className="evidence-group" open>
      <summary>
        {agentLabel} · {totalCount}
      </summary>
      {totalCount === 0 ? <p className="muted-text">{t(lang, "report.noRetrievalHits")}</p> : null}
      {groups.map((fileGroup) => (
        <section key={`${agentLabel}-${fileGroup.filename}`} className="evidence-file-group">
          <h4>
            {t(lang, "report.groupedByFile")}: {evidenceFilenameLabel(lang, fileGroup.filename)}
          </h4>
          {fileGroup.bySourceType.map(({ sourceType, items }) => (
            <div key={`${fileGroup.filename}-${sourceType}`} className="evidence-type-group">
              <div className="evidence-type-label">
                {sourceTypeLabel(lang, sourceType)} · {items.length}
              </div>
              {items.map((item, index) => (
                <article key={`${sourceType}-${index}`} className="evidence-hit">
                  <header>
                    <strong>{item.filename ? evidenceFilenameLabel(lang, item.filename) : t(lang, "report.unknownSource")}</strong>
                    <span>
                      {sourceTypeLabel(lang, item.source_type)}
                      {typeof item.score === "number" ? ` · ${item.score.toFixed(3)}` : ""}
                    </span>
                  </header>
                  <p>{item.text || t(lang, "report.noSnippet")}</p>
                  {item.raw_ref ? <code>{item.raw_ref}</code> : null}
                </article>
              ))}
            </div>
          ))}
        </section>
      ))}
    </details>
  );
}

function JsonBlock({ value, title }: { value: unknown; title?: string }) {
  return (
    <details className="json-block" open={!title}>
      <summary>{title ?? "JSON"}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default App;
