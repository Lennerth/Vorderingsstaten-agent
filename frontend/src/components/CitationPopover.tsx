import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { Camera, FileText, ImageIcon } from "lucide-react";
import type { Agent2Bestekpost } from "../api/types";
import { t, type Lang } from "../lib/i18n";

const PANEL_GAP = 6;
const VIEWPORT_PAD = 12;

type PanelPosition = { top: number; left: number };

function computePanelPosition(trigger: DOMRect, panel: HTMLElement): PanelPosition {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const width = panel.offsetWidth;
  const height = panel.offsetHeight;

  let left = trigger.left;
  left = Math.max(VIEWPORT_PAD, Math.min(left, vw - width - VIEWPORT_PAD));

  const spaceBelow = vh - trigger.bottom - VIEWPORT_PAD;
  const spaceAbove = trigger.top - VIEWPORT_PAD;
  let top: number;
  if (spaceBelow >= height + PANEL_GAP || spaceBelow >= spaceAbove) {
    top = trigger.bottom + PANEL_GAP;
  } else {
    top = trigger.top - height - PANEL_GAP;
  }
  top = Math.max(VIEWPORT_PAD, Math.min(top, vh - VIEWPORT_PAD - height));

  return { top, left };
}

type Props = {
  lang: Lang;
  post: Agent2Bestekpost;
  fragment?: string;
  children: ReactNode;
};

export function CitationPopover({ lang, post, fragment, children }: Props) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<PanelPosition | null>(null);
  const panelId = useId();
  const rootRef = useRef<HTMLSpanElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!open) {
      setPosition(null);
      return;
    }

    const trigger = rootRef.current;
    const panel = panelRef.current;
    if (!trigger || !panel) return;

    const updatePosition = () => {
      const nextTrigger = rootRef.current;
      const nextPanel = panelRef.current;
      if (!nextTrigger || !nextPanel) return;
      setPosition(computePanelPosition(nextTrigger.getBoundingClientRect(), nextPanel));
    };

    updatePosition();
    window.addEventListener("scroll", updatePosition, true);
    window.addEventListener("resize", updatePosition);
    return () => {
      window.removeEventListener("scroll", updatePosition, true);
      window.removeEventListener("resize", updatePosition);
    };
  }, [open, fragment, post.bron?.bestandsnaam, post.bron?.sectie, post.camera_labels, post.image_indices]);

  useEffect(() => {
    if (!open) return;
    function onDocClick(event: MouseEvent) {
      const target = event.target as Node;
      if (rootRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setOpen(false);
    }
    function onEsc(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  const cameras = post.camera_labels ?? [];
  const indices = post.image_indices ?? [];

  const panel =
    open ? (
      <div
        ref={panelRef}
        id={panelId}
        className="citation-panel citation-panel--portal"
        role="dialog"
        aria-label={t(lang, "citation.title")}
        style={
          position
            ? { top: position.top, left: position.left, visibility: "visible" }
            : { top: 0, left: 0, visibility: "hidden" }
        }
      >
        <p className="citation-note">{t(lang, "citation.note")}</p>
        {cameras.length > 0 ? (
          <div className="citation-row">
            <Camera size={14} />
            <span>{cameras.join(", ")}</span>
          </div>
        ) : null}
        {indices.length > 0 ? (
          <div className="citation-row">
            <ImageIcon size={14} />
            <span>#{indices.join(", #")}</span>
          </div>
        ) : null}
        {post.bron?.bestandsnaam ? (
          <div className="citation-row">
            <FileText size={14} />
            <span>{post.bron.bestandsnaam}</span>
          </div>
        ) : null}
        {post.bron?.sectie ? <div className="citation-row muted">{post.bron.sectie}</div> : null}
        {fragment ? <blockquote className="citation-fragment">{fragment}</blockquote> : null}
        {!fragment && post.bron?.fragmenten?.[0] ? (
          <blockquote className="citation-fragment">{post.bron.fragmenten[0]}</blockquote>
        ) : null}
      </div>
    ) : null;

  return (
    <span className="citation-wrap" ref={rootRef}>
      <button
        type="button"
        className="citation-trigger"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={t(lang, "citation.clickHint")}
        title={t(lang, "citation.clickHint")}
        onClick={() => setOpen((v) => !v)}
      >
        {children}
      </button>
      {panel ? createPortal(panel, document.body) : null}
    </span>
  );
}
