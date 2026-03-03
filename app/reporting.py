"""Render Agent 2 structured output into the Markdown report template."""

from __future__ import annotations

from app.models import Agent2Output

_HEADER = """\
# Vorderingsstaat – Automatisch concept

## Input
- Foto's: Foto 1 (voor) → Foto 2 (na)
- Datum/tijd: {datum}

---
"""


def render_markdown(
    output: Agent2Output,
    datum: str = "automatisch gegenereerd",
) -> str:
    parts: list[str] = [_HEADER.format(datum=datum)]

    for tr in output.transitions:
        parts.append(f"## Overgang: Foto {tr.from_photo} → Foto {tr.to_photo}")
        parts.append(f"**Zekerheid:** {tr.zekerheid}  ")
        parts.append(f"**Korte samenvatting:** {tr.samenvatting}\n")

        for bp in tr.bestekposten:
            parts.append(f"### Bestekpost {bp.nummer} – {bp.titel}")

            parts.append("**Zichtbaar uitgevoerd**")
            for item in bp.zichtbaar_uitgevoerd:
                parts.append(f"- {item}")
            parts.append("")

            parts.append("**Relevante bestekeisen / uitvoering / controle**")
            for item in bp.bestekeisen:
                parts.append(f"- {item}")
            parts.append("")

            parts.append("**Bron (detailbestek)**")
            parts.append(f"- Deel: {bp.bron.deel}")
            parts.append(f"- Sectie: {bp.bron.sectie}")
            parts.append("- Fragmenten:")
            for frag in bp.bron.fragmenten:
                parts.append(f'  - "{frag}"')
            parts.append("")

            parts.append("**Open punten / risico's**")
            for item in bp.open_punten:
                parts.append(f"- {item}")
            parts.append("")

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
