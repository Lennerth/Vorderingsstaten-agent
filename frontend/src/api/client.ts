import {
  ApiError,
  type MediaTrack,
  type ProgressJob,
  type ReportRequest,
  type ServerConfig,
} from "./types";

const baseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/+$/, "") ?? "";

async function readError(res: Response): Promise<string> {
  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const data = (await res.json().catch(() => null)) as { detail?: unknown } | null;
    if (typeof data?.detail === "string") return data.detail;
    if (data?.detail) return JSON.stringify(data.detail);
  }
  return (await res.text().catch(() => "")).slice(0, 500);
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${baseUrl}${path}`, init);
  } catch (error) {
    throw new ApiError("Network error: could not reach the FastAPI backend.", undefined, String(error));
  }
  if (!res.ok) {
    const detail = await readError(res);
    throw new ApiError(detail || `Request failed with HTTP ${res.status}.`, res.status, detail);
  }
  return (await res.json()) as T;
}

export async function fetchConfig(): Promise<ServerConfig> {
  return requestJson<ServerConfig>("/config");
}

export async function startProgressReportJob(request: ReportRequest): Promise<{ request_id: string; status: string }> {
  return requestJson<{ request_id: string; status: string }>("/progress-report/jobs", {
    method: "POST",
    body: buildReportFormData(request),
  });
}

export async function fetchProgress(requestId: string): Promise<ProgressJob> {
  return requestJson<ProgressJob>(`/progress/${encodeURIComponent(requestId)}`);
}

export function buildReportFormData(request: ReportRequest): FormData {
  const form = new FormData();
  const pairLabels: string[] = [];
  const videoLabels: string[] = [];
  const frameCounts: number[] = [];
  const trackOrder: string[] = [];

  for (const track of request.tracks) {
    trackOrder.push(track.kind);
    if (track.kind === "pair") {
      appendPair(form, track);
      pairLabels.push(track.label);
    } else {
      if (!track.video) {
        throw new ApiError(`Timelapse track "${track.label}" is missing a video file.`);
      }
      form.append("videos", track.video, track.video.name);
      videoLabels.push(track.label);
      frameCounts.push(track.frameCount);
    }
  }

  form.append("camera_labels", JSON.stringify(pairLabels));
  form.append("video_labels", JSON.stringify(videoLabels));
  form.append("video_frame_counts", JSON.stringify(frameCounts));
  form.append("track_order", JSON.stringify(trackOrder));
  form.append("region", request.region);
  form.append("bestekpost_filter", request.bestekpostFilter);
  form.append("report_fields", JSON.stringify(request.reportFields));
  form.append("compression_preset", request.compression.preset);
  form.append("compression_advanced", request.compression.advanced ? "true" : "");
  if (request.compression.advanced) {
    form.append("jpeg_quality", String(request.compression.jpegQuality));
    form.append("target_image_mb", String(request.compression.targetImageMb));
  }

  return form;
}

function appendPair(form: FormData, track: Extract<MediaTrack, { kind: "pair" }>) {
  if (!track.before || !track.after) {
    throw new ApiError(`Camera track "${track.label}" is missing before or after image.`);
  }
  form.append("before_images", track.before, track.before.name);
  form.append("after_images", track.after, track.after.name);
}
