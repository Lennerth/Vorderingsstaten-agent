"""Render Agent 2 structured output into the Markdown report template."""

from __future__ import annotations

from collections import defaultdict
from app.models import Agent2Output


def render_markdown(
    output: Agent2Output,
    images: list[tuple[int, str, str, str]],
    datum: str = "automatisch gegenereerd",
) -> str:
    parts: list[str] = [
        "# Vorderingsstaat – Automatisch concept\n",
        "*(Dit rapport bevat uitsluitend werk dat nieuw is uitgevoerd of gewijzigd tussen de voor- en na-foto's)*\n",
        "## Input",
        f"- Datum/tijd: {datum}"
    ]

    # Build the camera header
    # images is [(idx, camera_label, role, data_url), ...]
    camera_map = defaultdict(dict)
    for idx, label, role, _ in images:
        camera_map[label][role] = idx
        
    for label, roles in camera_map.items():
        voor_idx = roles.get("voor", "?")
        na_idx = roles.get("na", "?")
        parts.append(f"- {label}: Foto {voor_idx} (voor) → Foto {na_idx} (na)")
    
    parts.append("\n---\n")
    
    # Per-camera overview section. Only render if Agent 2 returned camera labels.
    camera_to_bps = defaultdict(list)
    for bp in output.bestekposten:
        for label in bp.camera_labels or []:
            camera_to_bps[label].append(bp.nummer)

    if camera_to_bps:
        parts.append("## Overzicht per camera\n")
        for label in camera_map.keys():
            bps = camera_to_bps.get(label, [])
            if bps:
                bps_str = ", ".join(bps)
                parts.append(f"- **{label}**: {bps_str}")
            else:
                parts.append(f"- **{label}**: Geen bestekposten gedetecteerd")

        parts.append("\n---\n")

    # Bestekposten detail section
    parts.append("## Bestekposten\n")

    for bp in output.bestekposten:
        parts.append(f"### Bestekpost {bp.nummer} – {bp.titel}")
        
        if bp.camera_labels is not None or bp.image_indices is not None:
            cameras_str = ", ".join(bp.camera_labels or []) if bp.camera_labels else "Onbekend"
            indices_str = ", ".join(map(str, bp.image_indices or [])) if bp.image_indices else "Onbekend"
            parts.append(f"**Camera's:** {cameras_str} (Foto's: {indices_str})")
        parts.append(f"**Zekerheid:** {bp.zekerheid}\n")

        if bp.zichtbaar_uitgevoerd is not None:
            parts.append("**Uitgevoerd in deze periode**")
            for item in bp.zichtbaar_uitgevoerd:
                parts.append(f"- {item}")
            parts.append("")

        if bp.bestekeisen is not None:
            parts.append("**Relevante bestekeisen / uitvoering / controle**")
            for item in bp.bestekeisen:
                parts.append(f"- {item}")
            parts.append("")

        if bp.bron is not None:
            parts.append("**Bron (detailbestek)**")
            parts.append(f"- Deel: {bp.bron.deel}")
            parts.append(f"- Sectie: {bp.bron.sectie}")
            parts.append("- Fragmenten:")
            for frag in bp.bron.fragmenten:
                parts.append(f'  - "{frag}"')
            parts.append("")

        if bp.open_punten is not None:
            parts.append("**Open punten / risico's**")
            for item in bp.open_punten:
                parts.append(f"- {item}")
            parts.append("")

        if bp.volgende_stap is not None:
            parts.append("**Volgende stap**")
            parts.append(f"- {bp.volgende_stap}")
        parts.append("\n---\n")

    if output.aandachtspunten_globaal:
        parts.append("## Aandachtspunten (globaal)")
        for item in output.aandachtspunten_globaal:
            parts.append(f"- {item}")
        parts.append("")

    if output.extra_input_nodig:
        parts.append("## Aanbevolen extra input (indien zekerheid laag)")
        for item in output.extra_input_nodig:
            parts.append(f"- {item}")

    return "\n".join(parts)
