from pathlib import Path

p = Path(__file__).resolve().parent.parent / "README.md"
lines = p.read_text(encoding="utf-8").splitlines()
out = []
for line in lines:
    if "VECTOR_STORE_ID` | yes |" in line and "Populated automatically" in line:
        out.append(
            "| `VECTOR_STORE_ID_FLEMISH` | yes* | – | Vector store for the Flemish bestek. "
            "Set by `python -m scripts.init_kb --region flemish`. |"
        )
        out.append(
            "| `VECTOR_STORE_ID_WALLOON` | yes* | – | Vector store for the Walloon CCTB. "
            "Set by `python -m scripts.init_kb --region walloon`. |"
        )
        out.append(
            "| `VECTOR_STORE_ID` | no | – | Legacy fallback: used as `VECTOR_STORE_ID_FLEMISH` "
            "if the Flemish key is empty. |"
        )
        out.append("")
        out.append("\\* At least the store for the region you use must be set.")
    else:
        out.append(line)
p.write_text("\n".join(out) + "\n", encoding="utf-8")
print("README patched")
