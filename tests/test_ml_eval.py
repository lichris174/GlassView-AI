"""Eval harness: geometry, metrics, labels I/O, baselines' parsing, end-to-end run."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from PIL import Image

from glassview_ai.privacy.redact import find_spans
from ml import evaluate as E
from ml import metrics as M
from ml.baselines.ocr_regex import boxes_from_ocr
from ml.baselines.qwen_vl import parse_boxes
from ml.labels import Box, import_json_export, import_yolo_export, parse_yolo, to_yolo


def B(x1: float, y1: float, x2: float, y2: float, cls: str = "api_key", score: float = 1.0) -> Box:
    return Box(cls, x1, y1, x2, y2, score)


# --- geometry ----------------------------------------------------------------
def test_covered_area_counts_overlap_once() -> None:
    # Two 10x10 squares overlapping in a 5x10 strip: union = 150.
    assert M.covered_area([B(0, 0, 10, 10), B(5, 0, 15, 10)]) == 150


def test_covered_area_within_clips_to_target() -> None:
    target = [B(0, 0, 10, 10)]
    assert M.covered_area([B(5, 5, 20, 20)], target) == 25
    assert M.covered_area([B(20, 20, 30, 30)], target) == 0
    assert M.covered_area([], target) == 0


def test_iou() -> None:
    assert M.iou(B(0, 0, 10, 10), B(0, 0, 10, 10)) == 1
    assert M.iou(B(0, 0, 10, 10), B(5, 0, 15, 10)) == pytest.approx(50 / 150)
    assert M.iou(B(0, 0, 1, 1), B(2, 2, 3, 3)) == 0


# --- privacy metrics -----------------------------------------------------------
def test_region_protected_only_above_coverage() -> None:
    gt = [B(0, 0, 10, 10)]
    assert M.frame_stats("s", gt, [B(0, 0, 10, 9)]).gt_protected == {"api_key": 1}  # 90%
    assert M.frame_stats("s", gt, [B(0, 0, 10, 8)]).gt_protected == {}  # 80%
    # Two partial boxes that together cover it still count: blur is a union.
    assert M.frame_stats("s", gt, [B(0, 0, 5, 10), B(5, 0, 10, 10)]).gt_protected


def test_privacy_metrics_hand_computed() -> None:
    stats = [
        # Sensitive frame: 2 regions, 1 protected; prediction 200 px, 100 on GT.
        M.frame_stats("a", [B(0, 0, 10, 10), B(50, 50, 60, 60, "financial")],
                      [B(0, 0, 20, 10)]),
        M.frame_stats("b", [], [B(0, 0, 5, 5)]),  # clean frame, falsely blurred
        M.frame_stats("c", [], []),  # clean frame, left alone
    ]
    m = M.privacy_metrics(stats)
    assert m["region_recall"] == 0.5
    assert m["region_recall/api_key"] == 1.0
    assert m["region_recall/financial"] == 0.0
    assert math.isnan(m["region_recall/credential"])  # absent class is undefined, not 0
    assert m["pixel_recall"] == 100 / 200
    assert m["blur_precision"] == 100 / (200 + 25)
    assert m["clean_false_blur_rate"] == 0.5
    assert m["sensitive_frame_recall"] == 1.0


# --- detection AP ------------------------------------------------------------
def test_ap_perfect_and_zero() -> None:
    gt = [B(0, 0, 10, 10)]
    assert M.average_precision([(gt, [B(0, 0, 10, 10, score=0.9)])], "api_key") == 1.0
    assert M.average_precision([(gt, [])], "api_key") == 0.0
    assert math.isnan(M.average_precision([(gt, [])], "financial"))


def test_ap_ranks_by_score() -> None:
    # One true positive and one false positive. FP ranked first: precision 1/2 at
    # recall 1, so AP = 0.5. TP ranked first: AP = 1.0.
    gt = [B(0, 0, 10, 10)]
    tp, fp = B(0, 0, 10, 10, score=0.5), B(50, 50, 60, 60, score=0.9)
    assert M.average_precision([(gt, [tp, fp])], "api_key") == pytest.approx(0.5)
    tp_hi = B(0, 0, 10, 10, score=0.95)
    assert M.average_precision([(gt, [tp_hi, fp])], "api_key") == pytest.approx(1.0)


def test_duplicate_detection_counts_once() -> None:
    gt = [B(0, 0, 10, 10)]
    preds = [B(0, 0, 10, 10, score=0.9), B(0, 0, 10, 10, score=0.8)]
    assert M.average_precision([(gt, preds)], "api_key") == pytest.approx(1.0)


# --- threshold + bootstrap ---------------------------------------------------------
def test_choose_threshold_keeps_highest_that_meets_target() -> None:
    frames = [
        ("a", [B(0, 0, 10, 10)], [B(0, 0, 10, 10, score=0.9)]),
        ("b", [B(0, 0, 10, 10)], [B(0, 0, 10, 10, score=0.3)]),
    ]
    assert M.choose_threshold(frames, 0.5) == (0.9, 0.5, True)
    assert M.choose_threshold(frames, 1.0) == (0.3, 1.0, True)
    # An unreachable target is reported as a miss, not silently "met".
    missed = [("a", [B(0, 0, 10, 10), B(50, 50, 60, 60)], [B(0, 0, 10, 10, score=0.9)])]
    assert M.choose_threshold(missed, 1.0) == (0.9, 0.5, False)


def test_ap_with_tied_scores_ignores_frame_order() -> None:
    # Constant-score systems (OCR, VLM): AP must not depend on frame order.
    gt = [B(0, 0, 10, 10)]
    hit = (gt, [B(0, 0, 10, 10)])
    miss = ([B(0, 0, 10, 10)], [B(50, 50, 60, 60)])
    a = M.average_precision([hit, miss], "api_key")
    b = M.average_precision([miss, hit], "api_key")
    assert a == b == pytest.approx(0.25)  # one point: recall 1/2, precision 1/2


def test_voc_matching_counts_second_box_on_taken_gt_as_fp() -> None:
    # Prediction 2 overlaps GT-1 most, which is already taken: VOC calls it a
    # false positive even though it touches GT-2 a little.
    gts = [B(0, 0, 10, 10), B(9, 0, 19, 10)]
    preds = [B(0, 0, 10, 10, score=0.9), B(1, 0, 11, 10, score=0.8)]
    assert M.average_precision([(gts, preds)], "api_key") == pytest.approx(0.5)


def test_bootstrap_ci_contains_estimate_and_collapses_when_constant() -> None:
    stats = [M.frame_stats(f"s{i}", [B(0, 0, 10, 10)], [B(0, 0, 10, 10)]) for i in range(10)]
    def recall(st):  # noqa: ANN001, ANN202
        return M.privacy_metrics(st)["region_recall"]
    assert M.bootstrap_ci(stats, recall, n=200) == (1.0, 1.0)

    mixed = stats[:5] + [M.frame_stats(f"t{i}", [B(0, 0, 10, 10)], []) for i in range(5)]
    lo, hi = M.bootstrap_ci(mixed, recall, n=500)
    assert lo < 0.5 < hi


def test_paired_diff_detects_consistent_improvement() -> None:
    gts = [B(0, 0, 10, 10)]
    better = [M.frame_stats(f"s{i}", gts, [B(0, 0, 10, 10)]) for i in range(20)]
    worse = [M.frame_stats(f"s{i}", gts, [] if i % 2 else [B(0, 0, 10, 10)]) for i in range(20)]
    def recall(st):  # noqa: ANN001, ANN202
        return M.privacy_metrics(st)["region_recall"]
    d, lo, hi = M.paired_bootstrap_diff(better, worse, recall, n=500)
    assert d == 0.5 and lo > 0
    with pytest.raises(ValueError):
        M.paired_bootstrap_diff(better, worse[:-1], recall)


def test_zero_area_ground_truth_is_ignored() -> None:
    # A degenerate (zero-width) label cannot be blurred or matched; it must not
    # count as a missed region or cap AP below 1.
    gts = [B(0, 0, 10, 10), B(5, 5, 5, 9)]
    pred = [B(0, 0, 10, 10, score=0.9)]
    assert M.average_precision([(gts, pred)], "api_key") == pytest.approx(1.0)
    st = M.frame_stats("s", gts, pred)
    assert st.gt_count == {"api_key": 1} and st.gt_degenerate == 1
    assert M.privacy_metrics([st])["region_recall"] == 1.0
    # A frame whose only label is degenerate is clean.
    assert M.frame_stats("s", [B(5, 5, 5, 9)], []).clean


def test_clip_boxes_to_image() -> None:
    preds = [B(-10, -10, 10, 10), B(-100, -100, -90, -90), B(95, 95, 120, 120)]
    clipped = M.clip_boxes(preds, 100, 100)
    assert [(b.x1, b.y1, b.x2, b.y2) for b in clipped] == [(0, 0, 10, 10), (95, 95, 100, 100)]
    # Off-screen area no longer dilutes blur precision.
    st = M.frame_stats("s", [B(0, 0, 10, 10)], M.clip_boxes([B(0, 0, 10, 10), preds[1]], 100, 100))
    assert M.privacy_metrics([st])["blur_precision"] == 1.0


def test_bootstrap_reports_undefined_replicates() -> None:
    # One clean session out of five: replicates that miss it have no clean
    # frames, so the false-blur rate is undefined there. Those replicates must
    # be counted, and with this many of them the interval is undefined rather
    # than a degenerate (1, 1).
    stats = [M.frame_stats("s0", [], [B(0, 0, 1, 1)])] + [
        M.frame_stats(f"s{i}", [B(0, 0, 1, 1)], []) for i in range(1, 5)
    ]
    def rate(st):  # noqa: ANN001, ANN202
        return M.privacy_metrics(st)["clean_false_blur_rate"]
    iv = M.bootstrap_interval(stats, rate, n=500)
    assert iv.n == 500 and 0 < iv.undefined < 500
    assert math.isnan(iv.lo) and math.isnan(iv.hi)
    lo, hi = M.bootstrap_ci(stats, rate, n=500)  # tuple API unchanged
    assert math.isnan(lo) and math.isnan(hi)
    # Fully defined metric: nothing dropped.
    def sfr(st):  # noqa: ANN001, ANN202
        return M.privacy_metrics(st)["sensitive_frame_recall"]
    full = M.bootstrap_interval(stats, sfr, n=200)
    assert full.undefined == 0 and (full.lo, full.hi) == (0.0, 0.0)
    d, piv = M.paired_bootstrap_interval(stats, stats, rate, n=200)
    assert d == 0.0 and piv.undefined > 0


# --- labels ------------------------------------------------------------------
def test_yolo_round_trip() -> None:
    boxes = [B(100, 50, 300, 150, "financial")]
    back = parse_yolo(to_yolo(boxes, 1000, 500), 1000, 500)
    assert back[0].cls == "financial"
    assert (back[0].x1, back[0].y1, back[0].x2, back[0].y2) == pytest.approx((100, 50, 300, 150))
    assert parse_yolo("", 10, 10) == []
    with pytest.raises(ValueError):
        parse_yolo("9 0.5 0.5 0.1 0.1", 10, 10)


def test_import_matches_label_studio_renamed_files(tmp_path: Path) -> None:
    raw, export, dest = tmp_path / "raw", tmp_path / "export", tmp_path / "labels"
    (raw / "bank-01").mkdir(parents=True)
    Image.new("RGB", (10, 10)).save(raw / "bank-01" / "20261014-101010-001.png")
    (export / "labels").mkdir(parents=True)
    (export / "classes.txt").write_text(
        "credential\napi_key\nfinancial\nprivate_message\npersonal_id\n"
    )
    (export / "labels" / "a1b2c3-20261014-101010-001.txt").write_text("2 0.5 0.5 0.2 0.2\n")
    (export / "labels" / "zz-unknown.txt").write_text("")
    n, problems = import_yolo_export(export, raw, dest)
    assert n == 1 and (dest / "bank-01" / "20261014-101010-001.txt").exists()
    assert problems == ["zz-unknown.txt: no frame match"]


def test_import_remaps_class_ids_by_name(tmp_path: Path) -> None:
    raw, export, dest = tmp_path / "raw", tmp_path / "export", tmp_path / "labels"
    (raw / "s").mkdir(parents=True)
    Image.new("RGB", (10, 10)).save(raw / "s" / "f1.png")
    (export / "labels").mkdir(parents=True)
    # Alphabetical order, as Label Studio may export: id 0 is api_key here.
    (export / "classes.txt").write_text(
        "api_key\ncredential\nfinancial\npersonal_id\nprivate_message\n"
    )
    (export / "labels" / "x-f1.txt").write_text("0 0.5 0.5 0.2 0.2\n4 0.1 0.1 0.1 0.1\n")
    import_yolo_export(export, raw, dest)
    ids = [line.split()[0] for line in (dest / "s" / "f1.txt").read_text().splitlines()]
    assert ids == ["1", "3"]  # api_key and private_message in CLASSES order


def test_import_rejects_unknown_class(tmp_path: Path) -> None:
    (tmp_path / "labels").mkdir()
    (tmp_path / "classes.txt").write_text("face\n")
    with pytest.raises(SystemExit):
        import_yolo_export(tmp_path, tmp_path, tmp_path / "out")


def _json_task(stem: str, cls: str) -> dict:
    box = {"value": {"x": 10, "y": 20, "width": 40, "height": 10, "rectanglelabels": [cls]}}
    return {"data": {"image": f"/data/upload/4/ab-s1__{stem}.png"},
            "annotations": [{"was_cancelled": False, "result": [box]}]}


def _one_session_raw(tmp_path: Path, stems: tuple[str, ...]) -> Path:
    raw = tmp_path / "raw"
    (raw / "s1").mkdir(parents=True)
    for stem in stems:
        Image.new("RGB", (10, 10)).save(raw / "s1" / f"{stem}.png")
    return raw


def test_json_import_validates_every_task_before_writing(tmp_path: Path) -> None:
    raw = _one_session_raw(tmp_path, ("20261020-000001-001", "20261020-000002-002"))
    dest = tmp_path / "labels"
    tasks = [_json_task("20261020-000001-001", "financial"),
             _json_task("20261020-000002-002", "face")]
    with pytest.raises(SystemExit, match="face"):
        import_json_export(tasks, raw, dest)
    assert not list(dest.rglob("*.txt"))  # nothing half-imported


def test_yolo_import_validates_every_file_before_writing(tmp_path: Path) -> None:
    raw = _one_session_raw(tmp_path, ("f1", "f2"))
    export, dest = tmp_path / "export", tmp_path / "labels"
    (export / "labels").mkdir(parents=True)
    (export / "labels" / "a-f1.txt").write_text("2 0.5 0.5 0.2 0.2\n")
    (export / "labels" / "b-f2.txt").write_text("9 0.5 0.5 0.2 0.2\n")  # no class 9
    with pytest.raises(SystemExit, match="9"):
        import_yolo_export(export, raw, dest)
    assert not list(dest.rglob("*.txt"))
    # Malformed lines (wrong field count, non-numeric) also abort before writing.
    for bad in ("2 0.5 0.5 0.2\n", "x 0.5 0.5 0.2 0.2\n", "2 0.5 abc 0.2 0.2\n"):
        (export / "labels" / "b-f2.txt").write_text(bad)
        with pytest.raises(SystemExit):
            import_yolo_export(export, raw, dest)
        assert not list(dest.rglob("*.txt")), bad


def test_import_reports_conflicting_entries_for_one_frame(tmp_path: Path) -> None:
    stem = "20261020-000001-001"
    raw, dest = _one_session_raw(tmp_path, (stem,)), tmp_path / "labels"
    agree = [_json_task(stem, "financial"), _json_task(stem, "financial")]
    assert import_json_export(agree, raw, dest)[0] == 1
    disagree = [_json_task(stem, "financial"), _json_task(stem, "api_key")]
    n, problems = import_json_export(disagree, raw, tmp_path / "other")
    assert n == 0 and "disagree" in problems[0]
    assert not (tmp_path / "other").exists()


def test_import_refuses_to_overwrite_edited_labels_without_force(tmp_path: Path) -> None:
    # Re-importing a stale export must not silently undo hand corrections.
    stem = "20261020-000001-001"
    raw = _one_session_raw(tmp_path, (stem,))
    dest = tmp_path / "labels"
    tasks = [_json_task(stem, "financial")]
    import_json_export(tasks, raw, dest)
    label = dest / "s1" / f"{stem}.txt"
    original = label.read_text()
    assert import_json_export(tasks, raw, dest)[0] == 1  # identical re-import is fine

    label.write_text("4 0.5 0.5 0.1 0.1\n")  # corrected by hand after the export
    with pytest.raises(SystemExit, match="--force"):
        import_json_export(tasks, raw, dest)
    assert label.read_text() == "4 0.5 0.5 0.1 0.1\n"
    import_json_export(tasks, raw, dest, force=True)
    assert label.read_text() == original
    # Same boxes written with different rounding/formatting is not a conflict.
    label.write_text("2 0.3 0.25 0.4 0.1\n")
    assert import_json_export(tasks, raw, dest)[0] == 1

    export = tmp_path / "export"
    (export / "labels").mkdir(parents=True)
    (export / "labels" / f"x-{stem}.txt").write_text("0 0.5 0.5 0.2 0.2\n")
    with pytest.raises(SystemExit, match="--force"):
        import_yolo_export(export, raw, dest)
    assert label.read_text() == original


# --- baselines' pure parts -------------------------------------------------------
def test_find_spans_maps_value_not_label() -> None:
    text = "api_key = abcdef123456"
    kind, s, e = find_spans(text)[0]
    assert kind == "SECRET" and text[s:e] == "abcdef123456"


def test_ocr_boxes_cover_only_matched_words() -> None:
    words = ["token:", "ghp_" + "a" * 36, "hello"]
    data = {
        "text": words, "block_num": [1, 1, 1], "par_num": [1, 1, 1], "line_num": [1, 1, 1],
        "word_num": [1, 2, 3], "left": [0, 70, 400], "top": [10, 10, 10],
        "width": [60, 300, 50], "height": [12, 12, 12],
    }
    boxes = boxes_from_ocr(data)
    assert len(boxes) == 1
    assert (boxes[0].cls, boxes[0].x1, boxes[0].x2) == ("api_key", 70, 370)


def test_qwen_parse_scales_grid_and_tolerates_noise() -> None:
    reply = 'Sure:\n```json\n[{"label": "API key", "bbox_2d": [500, 0, 250, 1000]}]\n```'
    (box,) = parse_boxes(reply, 2000, 1000)
    assert box.cls == "api_key"
    assert (box.x1, box.y1, box.x2, box.y2) == (500, 0, 1000, 1000)  # corners re-sorted
    assert parse_boxes("no boxes here", 10, 10) == []
    assert parse_boxes("[{bad json", 10, 10) == []
    assert parse_boxes('[{"label": "x", "bbox_2d": [1, 2]}]', 10, 10) == []


def test_qwen_parse_salvages_truncated_reply() -> None:
    # Cut off by the token limit: the first complete object still counts.
    reply = ('Regions [see below]: [{"label": "financial", "bbox_2d": [0, 0, 100, 100]}, '
             '{"label": "api_key", "bbox_2d": [5')
    (box,) = parse_boxes(reply, 1000, 1000)
    assert box.cls == "financial" and box.x2 == 100


def test_import_writes_empty_label_for_image_without_boxes(tmp_path: Path) -> None:
    raw, export, dest = tmp_path / "raw", tmp_path / "export", tmp_path / "labels"
    (raw / "clean-01").mkdir(parents=True)
    Image.new("RGB", (10, 10)).save(raw / "clean-01" / "20261014-111111-002.png")
    (export / "labels").mkdir(parents=True)
    (export / "images").mkdir()
    Image.new("RGB", (10, 10)).save(export / "images" / "ff-20261014-111111-002.png")
    n, _ = import_yolo_export(export, raw, dest)
    label = dest / "clean-01" / "20261014-111111-002.txt"
    assert n == 1 and label.read_text() == ""


def test_json_import_converts_boxes_and_handles_clean_and_skipped(tmp_path: Path) -> None:
    raw, dest = tmp_path / "raw", tmp_path / "labels"
    (raw / "s1").mkdir(parents=True)
    for stem in ("20261020-000001-001", "20261020-000002-002", "20261020-000003-003"):
        Image.new("RGB", (10, 10)).save(raw / "s1" / f"{stem}.png")
    box = {"value": {"x": 10, "y": 20, "width": 40, "height": 10,
                     "rectanglelabels": ["financial"]}}
    tasks = [
        {"data": {"image": "/data/upload/4/ab12-s1__20261020-000001-001.png"},
         "annotations": [{"was_cancelled": False, "result": [box]}]},
        {"data": {"image": "/data/upload/4/cd34-s1__20261020-000002-002.png"},
         "annotations": [{"was_cancelled": False, "result": []}]},
        {"data": {"image": "/data/upload/4/ef56-s1__20261020-000003-003.png"},
         "annotations": [{"was_cancelled": True, "result": []}]},
    ]
    n, problems = import_json_export(tasks, raw, dest)
    assert n == 2 and len(problems) == 1 and "skipped" in problems[0]
    expected = "2 0.300000 0.250000 0.400000 0.100000\n"
    assert (dest / "s1" / "20261020-000001-001.txt").read_text() == expected
    assert (dest / "s1" / "20261020-000002-002.txt").read_text() == ""
    assert not (dest / "s1" / "20261020-000003-003.txt").exists()


# --- end to end --------------------------------------------------------------
class FakeDetector:
    name = "fake"
    config = {"kind": "test"}

    def predict(self, image: Image.Image) -> list[Box]:
        return [B(0, 0, 50, 50, score=0.8)]


class SilentDetector:
    name = "silent"
    config = {"kind": "test"}

    def predict(self, image: Image.Image) -> list[Box]:
        return []


def _dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Six 2-frame sessions with a frozen split; returns the labels dir."""
    from ml.splits import assign

    monkeypatch.setenv("GLASSVIEW_DATA", str(tmp_path / "data"))
    monkeypatch.setattr(E, "RESULTS", tmp_path / "results")
    raw = tmp_path / "data" / "raw"
    labels = tmp_path / "data" / "labels"
    for s in range(6):
        (raw / f"s{s}").mkdir(parents=True)
        (labels / f"s{s}").mkdir(parents=True)
        for f in range(2):
            Image.new("RGB", (100, 100), (s * 40, f * 90, 0)).save(raw / f"s{s}" / f"{f}.png")
            # Even frames have a region the fake detector covers; odd ones are clean.
            (labels / f"s{s}" / f"{f}.txt").write_text("" if f else "1 0.25 0.25 0.5 0.5\n")
    assign(raw, tmp_path / "data" / "splits.json", 0.35, 0.15, seed=0)
    return labels


def test_run_writes_manifest_predictions_and_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    labels = _dataset(tmp_path, monkeypatch)
    out = E.run(FakeDetector(), "test", threshold=0.5, allow_partial=False)
    manifest = json.loads((out / "manifest.json").read_text())
    result = json.loads((out / "metrics.json").read_text())
    assert manifest["system"] == "fake" and manifest["split"]["split"] == "test"
    assert "git_commit" in manifest and "finished_at" in manifest
    assert result["metrics"]["region_recall"] == 1.0
    assert result["metrics"]["clean_false_blur_rate"] == 1.0
    assert result["ci95"]["region_recall"] == [1.0, 1.0]

    # Raising the threshold above the detector's score removes every box from
    # the privacy metrics, but AP still sees all predictions.
    rescored = E.score(out, threshold=0.9)
    assert rescored["metrics"]["region_recall"] == 0.0
    assert rescored["metrics"]["ap50/api_key"] == result["metrics"]["ap50/api_key"]
    assert (out / "metrics-t0.9.json").exists()
    assert rescored["labels_changed_since_run"] is False

    # Editing a label after the run is flagged at scoring time.
    test_frame = json.loads((out / "predictions.jsonl").read_text().splitlines()[0])["frame"]
    (labels / test_frame).with_suffix(".txt").write_text("0 0.5 0.5 0.1 0.1\n")
    changed = E.score(out, threshold=0.5)
    assert changed["labels_changed_since_run"] is True
    assert changed["labels_changed_frames"] == [test_frame]

    # A zero-area label is ignored by the metrics but counted in the output.
    (labels / test_frame).with_suffix(".txt").write_text("0 0.5 0.5 0.0 0.1\n")
    assert E.score(out, threshold=0.5)["num_degenerate_gt_ignored"] == 1

    # Scores keep full precision in predictions (rounding creates ties).
    row = json.loads((out / "predictions.jsonl").read_text().splitlines()[0])
    assert row["boxes"][0]["score"] == 0.8


def test_partial_predictions_do_not_flag_labels_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An interrupted run leaves fewer predictions than labeled frames. Scoring
    # it must compare labels frame by frame, not hash a different frame set.
    _dataset(tmp_path, monkeypatch)
    out = E.run(FakeDetector(), "test", threshold=0.5, allow_partial=False)
    rows = (out / "predictions.jsonl").read_text().splitlines()
    (out / "predictions.jsonl").write_text("\n".join(rows[:-1]) + "\n")
    result = E.score(out, threshold=0.5)
    assert result["num_frames"] == len(rows) - 1
    assert result["labels_changed_since_run"] is False

    # Manifests written before per-frame digests still score (legacy hash).
    manifest = json.loads((out / "manifest.json").read_text())
    del manifest["split"]["label_digests"]
    (out / "manifest.json").write_text(json.dumps(manifest))
    (out / "predictions.jsonl").write_text("\n".join(rows) + "\n")
    assert E.score(out, threshold=0.5)["labels_changed_since_run"] is False


def test_manual_threshold_never_overwrites_run_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dataset(tmp_path, monkeypatch)
    out = E.run(FakeDetector(), "test", threshold=0.5, allow_partial=False)
    original = (out / "metrics.json").read_text()
    assert json.loads(original)["threshold_source"] == "fixed"

    # --threshold alone, a new value: its own file, recorded as manual.
    E.main(["score", str(out), "--threshold", "0.9"])
    assert (out / "metrics.json").read_text() == original
    manual = json.loads((out / "metrics-t0.9.json").read_text())
    assert manual["threshold"] == 0.9 and manual["threshold_source"].startswith("manual")

    # --coverage alone: another operating point (own file), but the threshold
    # is still the run's, so its provenance is kept.
    E.main(["score", str(out), "--coverage", "0.5"])
    assert (out / "metrics.json").read_text() == original
    cov = json.loads((out / "metrics-t0.5-c0.5.json").read_text())
    assert cov["coverage"] == 0.5 and cov["threshold_source"] == "fixed"

    # Distinct thresholds never share a file name.
    assert E._metrics_name(0.4200001, 0.9) != E._metrics_name(0.42, 0.9)


def test_score_clips_off_image_predictions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Overhanging:
        name = "overhang"
        config: dict = {}

        def predict(self, image: Image.Image) -> list[Box]:
            # Exactly the 50x50 region once cut to the image; 150x150 if not.
            return [B(-100, -100, 50, 50, score=0.8)]

    _dataset(tmp_path, monkeypatch)
    out = E.run(Overhanging(), "test", threshold=0.5, allow_partial=False)
    m = json.loads((out / "metrics.json").read_text())["metrics"]
    # Half the frames are clean and also get the 2500 px box: 2500 / 5000.
    assert m["blur_precision"] == 0.5
    # Clipped, every region is matched (IoU 1; unclipped it is 2500/22500, AP 0);
    # the clean-frame boxes are tied false positives: recall 1 x precision 0.5.
    assert m["ap50/api_key"] == 0.5


def test_run_refuses_coverage_other_than_the_val_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _dataset(tmp_path, monkeypatch)
    val = E.run(FakeDetector(), "val", threshold=0.5, allow_partial=False)
    with pytest.raises(SystemExit, match="coverage"):
        E.main(["run", "--system", "block_all", "--split", "test",
                "--threshold-from", str(val), "--coverage", "0.5"])
    assert not list((tmp_path / "results").glob("*block_all*"))


def test_compare_never_calls_an_undefined_difference_significant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _dataset(tmp_path, monkeypatch)
    a = E.run(SilentDetector(), "test", threshold=0.5, allow_partial=False)
    b = E.run(FakeDetector(), "test", threshold=0.5, allow_partial=False)
    out = E.compare(a, b, 0.5, 0.5)
    # No predictions in run a: blur precision is undefined, so is the diff.
    assert out["blur_precision"]["diff"] is None
    assert out["blur_precision"]["significant"] is False
    assert out["region_recall"]["significant"] is True  # 0 vs 1 on every session
    assert out["coverage"] == M.DEFAULT_COVERAGE

    capsys.readouterr()
    E.main(["compare", str(a), str(b), "--coverage", "0.5"])
    assert json.loads(capsys.readouterr().out)["coverage"] == 0.5
