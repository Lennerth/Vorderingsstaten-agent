import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Camera, FileText, ImageIcon } from "lucide-react";
import type { Agent2Bestekpost } from "../api/types";
import { t, type Lang } from "../lib/i18n";

type Props = {
  lang: Lang;
  post: Agent2Bestekpost;
  fragment?: string;
  children: ReactNode;
};

export function CitationPopover({ lang, post, fragment, children }: Props) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const rootRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
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
      {open ? (
        <div id={panelId} className="citation-panel" role="dialog" aria-label={t(lang, "citation.title")}>
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
      ) : null}
    </span>
  );
}
