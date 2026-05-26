from app.output_storage import _create_next_output_dir, save_report_output


def test_create_next_output_dir_numeric_and_legacy(tmp_path):
    root = tmp_path / "outputs"
    root.mkdir()
    (root / "output one").mkdir()
    (root / "output 05").mkdir()
    created = _create_next_output_dir(root)
    assert created.name == "output 06"


def test_save_report_output_writes_artifacts(tmp_outputs_dir):
    result = {
        "markdown_report": "# Test",
        "agent1_json": {},
        "agent2_json": {},
        "evidence": {"agent1": [], "agent2": []},
    }
    tracks = [
        {
            "kind": "pair",
            "camera_label": "Cam 1",
            "before_filename": "a.jpg",
            "after_filename": "b.jpg",
        }
    ]
    out_dir = save_report_output(
        result,
        tracks,
        report_fields=["zichtbaar_uitgevoerd"],
        bestekpost_filters=[],
        region="flemish",
    )
    assert (out_dir / "report.md").is_file()
    assert (out_dir / "output.json").is_file()
    assert (out_dir / "evidence.json").is_file()
    assert (out_dir / "uploaded_images.txt").is_file()
