"""Render Agent 2 structured output into the Markdown report template."""

from __future__ import annotations

from collections import defaultdict

from app.models import Agent2Output
from app.regions import (
    CERTAINTY_LABELS,
    LOW_CONFIDENCE_WARNING,
    REPORT_LABELS,
    normalize_region,
)

_CONFIDENCE_BADGE_CLASS = {
    "hoog": "badge-high",
    "middel": "badge-medium",
    "laag": "badge-low",
}


def _confidence_badge_html(region: str, zekerheid: str) -> str:
    label = CERTAINTY_LABELS[region].get(zekerheid, zekerheid)
    css_class = _CONFIDENCE_BADGE_CLASS.get(zekerheid, "badge-medium")
    return f'<span class="badge {css_class}">{label}</span>'


def _format_bullet_item(text: str, region: str) -> str:
    warning = LOW_CONFIDENCE_WARNING[region]
    if warning.lower() in text.lower():
        return f'- <span class="warning-text">{text}</span>'
    return f"- {text}"


def render_markdown(
    output: Agent2Output,
    images: list[tuple[int, str, str, str]],
    datum: str | None = None,
    region: str = "flemish",
) -> str:
    region = normalize_region(region)
    L = REPORT_LABELS[region]
    if datum is None:
        datum = (
            "automatisch gegenereerd"
            if region == "flemish"
            else "généré automatiquement"
        )

    parts: list[str] = [
        L["title"],
        L["subtitle"],
        L["input"],
        L["date_time"].format(datum=datum),
    ]

    camera_map = defaultdict(dict)
    for idx, label, role, _ in images:
        camera_map[label][role] = idx

    for label, roles in camera_map.items():
        if "voor" in roles and "na" in roles:
            parts.append(
                L["photo_pair"].format(
                    label=label,
                    voor_idx=roles.get("voor", "?"),
                    na_idx=roles.get("na", "?"),
                )
            )
        else:
            t_roles = sorted(
                (key for key in roles if key.startswith("t=")),
                key=lambda key: float(key.removeprefix("t=")),
            )
            indices = ", ".join(str(roles[key]) for key in t_roles)
            timestamps = " … ".join(
                f"{key.removeprefix('t=')}s" for key in (t_roles[0], t_roles[-1])
            ) if t_roles else "?"
            parts.append(
                L["timelapse_track"].format(
                    label=label,
                    indices=indices,
                    timestamps=timestamps,
                )
            )

    parts.append("\n---\n")

    camera_to_bps = defaultdict(list)
    for bp in output.bestekposten:
        for label in bp.camera_labels or []:
            camera_to_bps[label].append(bp.nummer)

    if camera_to_bps:
        parts.append(L["overview_camera"])
        for label in camera_map.keys():
            bps = camera_to_bps.get(label, [])
            if bps:
                parts.append(L["camera_posts"].format(label=label, bps=", ".join(bps)))
            else:
                parts.append(L["no_posts"].format(label=label))

        parts.append("\n---\n")

    parts.append(L["bestekposten"])

    for bp in output.bestekposten:
        parts.append(L["post_header"].format(nummer=bp.nummer, titel=bp.titel))

        if bp.camera_labels is not None or bp.image_indices is not None:
            cameras_str = (
                ", ".join(bp.camera_labels or [])
                if bp.camera_labels
                else L["unknown"]
            )
            indices_str = (
                ", ".join(map(str, bp.image_indices or []))
                if bp.image_indices
                else L["unknown"]
            )
            parts.append(
                L["cameras"].format(cameras=cameras_str, indices=indices_str)
            )
        parts.append(
            L["zekerheid"].format(
                zekerheid=_confidence_badge_html(region, bp.zekerheid)
            )
        )
        parts.append("")

        if bp.zichtbaar_uitgevoerd is not None:
            parts.append(L["zichtbaar"])
            for item in bp.zichtbaar_uitgevoerd:
                parts.append(f"- {item}")
            parts.append("")

        if bp.bestekeisen is not None:
            parts.append(L["bestekeisen"])
            for item in bp.bestekeisen:
                parts.append(f"- {item}")
            parts.append("")

        if bp.bron is not None:
            parts.append(L["bron"])
            parts.append(L["bron_deel"].format(deel=bp.bron.deel))
            parts.append(L["bron_sectie"].format(sectie=bp.bron.sectie))
            if bp.bron.bestandsnaam:
                parts.append(
                    L["bron_bestandsnaam"].format(bestandsnaam=bp.bron.bestandsnaam)
                )
            parts.append(L["bron_fragmenten"])
            for frag in bp.bron.fragmenten:
                parts.append(f'  - "{frag}"')
            parts.append("")

        if bp.open_punten is not None:
            parts.append(L["open_punten"])
            for item in bp.open_punten:
                parts.append(_format_bullet_item(item, region))
            parts.append("")

        if bp.volgende_stap is not None:
            parts.append(L["volgende_stap"])
            parts.append(f"- {bp.volgende_stap}")
        parts.append("\n---\n")

    if output.aandachtspunten_globaal:
        parts.append(L["aandachtspunten"])
        for item in output.aandachtspunten_globaal:
            parts.append(f"- {item}")
        parts.append("")

    if output.extra_input_nodig:
        parts.append(L["extra_input"])
        for item in output.extra_input_nodig:
            parts.append(_format_bullet_item(item, region))

    return "\n".join(parts)
