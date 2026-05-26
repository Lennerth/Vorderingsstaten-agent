from app.output_storage import save_report_output


def test_timelapse_frames_saved_to_disk(tmp_outputs_dir, synthetic_image_bytes):
    result = {
        "markdown_report": "# Test",
        "agent1_json": {},
        "agent2_json": {},
        "evidence": {"agent1": [], "agent2": []},
        "extracted_frames": [],
    }
    tracks = [
        {
            "kind": "timelapse",
            "camera_label": "Cam TL",
            "video_filename": "clip.mp4",
            "frame_count": 2,
            "timestamps": [0.0, 5.0],
            "frame_jpeg_bytes": [synthetic_image_bytes[:5000], synthetic_image_bytes[:5000]],
        }
    ]
    out_dir = save_report_output(
        result,
        tracks,
        report_fields=[],
        bestekpost_filters=[],
        region="flemish",
    )
    frames_dir = out_dir / "frames" / "Cam_TL"
    saved = list(frames_dir.glob("frame_*.jpg"))
    assert len(saved) == 2
