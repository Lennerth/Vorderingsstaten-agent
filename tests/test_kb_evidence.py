from types import SimpleNamespace

from app.kb import (
    enrich_evidence_with_provenance_fallback,
    extract_retrieval_evidence,
    summarize_evidence_items,
)


def test_extract_retrieval_evidence_tool_call():
    result = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="file_search_call",
                id="call_1",
                results=[
                    SimpleNamespace(
                        filename="Deel-1.docx",
                        score=0.9,
                        content=[SimpleNamespace(type="text", text="snippet text")],
                    )
                ],
            )
        ]
    )
    items, stats = extract_retrieval_evidence(result)
    assert stats["tool_call_hits"] == 1
    assert "snippet text" in items[0]["text"]


def test_enrich_evidence_with_provenance_fallback():
    items = [{"filename": "Deel-1.docx", "text": "", "source_type": "citation"}]
    bestekposten = [
        {
            "bron": {
                "bestandsnaam": "Deel-1.docx",
                "fragmenten": ['"fallback fragment"'],
            }
        }
    ]
    enriched = enrich_evidence_with_provenance_fallback(items, bestekposten)
    assert enriched[0]["text"]
    assert enriched[0]["source_type"] == "citation_fallback"


def test_summarize_evidence_items_empty():
    summary = summarize_evidence_items([])
    assert summary["count"] == 0
