import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_ui_timelapse_submit_wiring():
    html = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert "let MAX_CAMERAS = 6" in html
    assert "MAX_PAIRS" not in html
    assert "formData.append('videos', videoFile)" in html
    assert "formData.append('video_labels', JSON.stringify(videoLabels))" in html
    assert "formData.append('video_frame_counts', JSON.stringify(videoFrameCounts))" in html
    assert "formData.append('track_order', JSON.stringify(trackOrder))" in html
    assert "fetch('/progress-report/jobs'" in html
    assert "pollProgress(" in html
    assert "getTrackKind(block)" in html
    assert 'id="extracted-frames-panel"' in html
    assert 'class="frame-count-input"' in html
    assert 'id="progress-panel"' in html
    assert "Frames geëxtraheerd uit timelapsevideo" in html
    assert "Images extraites de la vidéo timelapse" in html


def test_ui_i18n_keys_present_in_both_languages():
    html = (PROJECT_ROOT / "static" / "index.html").read_text(encoding="utf-8")
    i18n_keys = set(re.findall(r'data-i18n="([^"]+)"', html))
    placeholder_keys = set(re.findall(r'data-i18n-placeholder="([^"]+)"', html))

    script_match = re.search(r"const UI_TEXT = (\{.*?\n    \};)", html, re.S)
    assert script_match
    ui_blob = script_match.group(1)
    for key in i18n_keys | placeholder_keys:
        assert f"{key}:" in ui_blob or f"{key} :" in ui_blob
