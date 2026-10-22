"""Scoring for the sensitive-region detector and its baselines.

Two families of metrics, because the app uses the detector in two ways:

**Privacy metrics (what the product cares about).** The app blurs every
predicted box, regardless of its class, so these are class-agnostic on the
prediction side:

- *region recall*: share of ground-truth regions that end up protected. A
  region counts as protected when at least ``coverage`` (default 90%) of its
  area lies under the union of predicted boxes. Reported per ground-truth class.
- *pixel recall*: share of all sensitive pixels that get blurred.
- *blur precision*: share of blurred pixels that were actually sensitive
  (low means the answer loses context for nothing).
- *clean-frame false-blur rate*: share of frames with nothing sensitive that
  still get something blurred (or the whole request blocked, in block mode).
- *sensitive-frame recall*: share of frames with something sensitive that get
  at least one box. This is the metric for block mode.

**Detection metric (what ML readers expect).** Per-class average precision at
IoU 0.5 (VOC-style, all-point interpolation) and its mean, mAP@0.5. A system
that gives every box the same score (ocr_regex, qwen_vl, block_all) has a
single operating point, so its "AP" collapses to recall x precision at that
point. It is not comparable to the AP of a detector with real confidences;
compare those systems on the privacy metrics instead.

Ground-truth boxes with zero area (a slip of the labeling tool) are ignored
everywhere: they cannot be blurred or matched, so counting them would report a
miss no system could avoid.

Uncertainty: confidence intervals use a *cluster bootstrap over sessions*.
Frames in a session are near-copies, so resampling individual frames would
treat them as independent evidence and produce intervals that are too narrow.
Replicates where a metric is undefined (e.g. no clean frame was drawn) are left
out and counted; if more than ``MAX_UNDEFINED`` of them are, the interval is
undefined (NaN) rather than a misleadingly narrow one.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from .labels import CLASSES, Box

DEFAULT_COVERAGE = 0.9
# Share of bootstrap replicates allowed to be undefined before the interval is
# reported as undefined. Many undefined replicates mean the metric rests on one
# or two sessions, and the surviving replicates mostly repeat the same value.
MAX_UNDEFINED = 0.1


# --- geometry ----------------------------------------------------------------
def iou(a: Box, b: Box) -> float:
    ix = max(0.0, min(a.x2, b.x2) - max(a.x1, b.x1))
    iy = max(0.0, min(a.y2, b.y2) - max(a.y1, b.y1))
    inter = ix * iy
    union = a.area + b.area - inter
    return inter / union if union > 0 else 0.0


def covered_area(rects: Sequence[Box], within: Sequence[Box] | None = None) -> float:
    """Area of the union of ``rects``, optionally intersected with the union of
    ``within``. Exact, via coordinate compression: the plane is cut into cells
    along every box edge, and each cell is either fully in or fully out."""
    rects = [r for r in rects if r.area > 0]
    if not rects:
        return 0.0
    within = None if within is None else [w for w in within if w.area > 0]
    if within is not None and not within:
        return 0.0
    edges = list(rects) + (within or [])
    xs = sorted({v for r in edges for v in (r.x1, r.x2)})
    ys = sorted({v for r in edges for v in (r.y1, r.y2)})
    total = 0.0
    for x0, x1 in zip(xs, xs[1:], strict=False):
        cx = (x0 + x1) / 2
        for y0, y1 in zip(ys, ys[1:], strict=False):
            cy = (y0 + y1) / 2

            def hit(rs: Sequence[Box], cx: float = cx, cy: float = cy) -> bool:
                return any(r.x1 <= cx < r.x2 and r.y1 <= cy < r.y2 for r in rs)

            if hit(rects) and (within is None or hit(within)):
                total += (x1 - x0) * (y1 - y0)
    return total


def clip_boxes(boxes: Sequence[Box], width: float, height: float) -> list[Box]:
    """Boxes cut to the image. Area off the screen blurs nothing, so it must not
    count against blur precision; boxes left with no area are dropped."""
    out = []
    for b in boxes:
        c = Box(b.cls, max(0.0, b.x1), max(0.0, b.y1), min(width, b.x2), min(height, b.y2), b.score)
        if c.area > 0:
            out.append(c)
    return out


# --- per-frame statistics ------------------------------------------------------
@dataclass
class FrameStats:
    """Additive counts for one frame; dataset metrics are ratios of their sums."""

    session: str
    gt_count: dict[str, int] = field(default_factory=dict)
    gt_protected: dict[str, int] = field(default_factory=dict)
    gt_area: float = 0.0
    gt_covered: float = 0.0
    pred_area: float = 0.0
    pred_on_gt: float = 0.0
    any_pred: bool = False
    gt_degenerate: int = 0  # zero-area label boxes, ignored by every metric

    @property
    def clean(self) -> bool:
        return not self.gt_count


def frame_stats(
    session: str, gts: Sequence[Box], preds: Sequence[Box], coverage: float = DEFAULT_COVERAGE
) -> FrameStats:
    s = FrameStats(session=session, any_pred=bool(preds))
    for g in gts:
        if g.area <= 0:
            s.gt_degenerate += 1  # nothing to protect; counted so it gets fixed
            continue
        s.gt_count[g.cls] = s.gt_count.get(g.cls, 0) + 1
        if covered_area(preds, [g]) / g.area >= coverage:
            s.gt_protected[g.cls] = s.gt_protected.get(g.cls, 0) + 1
    s.gt_area = covered_area(gts)
    s.gt_covered = covered_area(preds, gts)
    s.pred_area = covered_area(preds)
    s.pred_on_gt = s.gt_covered  # same region: blurred AND sensitive
    return s


def _ratio(num: float, den: float) -> float:
    return num / den if den else math.nan


def privacy_metrics(stats: Sequence[FrameStats]) -> dict[str, float]:
    """Dataset-level privacy metrics from per-frame counts."""
    out: dict[str, float] = {}
    total = sum(sum(s.gt_count.values()) for s in stats)
    prot = sum(sum(s.gt_protected.values()) for s in stats)
    out["region_recall"] = _ratio(prot, total)
    for c in CLASSES:
        n = sum(s.gt_count.get(c, 0) for s in stats)
        out[f"region_recall/{c}"] = _ratio(sum(s.gt_protected.get(c, 0) for s in stats), n)
    out["pixel_recall"] = _ratio(sum(s.gt_covered for s in stats), sum(s.gt_area for s in stats))
    out["blur_precision"] = _ratio(
        sum(s.pred_on_gt for s in stats), sum(s.pred_area for s in stats)
    )
    clean = [s for s in stats if s.clean]
    sensitive = [s for s in stats if not s.clean]
    out["clean_false_blur_rate"] = _ratio(sum(s.any_pred for s in clean), len(clean))
    out["sensitive_frame_recall"] = _ratio(sum(s.any_pred for s in sensitive), len(sensitive))
    return out


# --- detection AP ------------------------------------------------------------
def average_precision(
    frames: Sequence[tuple[Sequence[Box], Sequence[Box]]], cls: str, iou_thr: float = 0.5
) -> float:
    """PASCAL VOC all-point AP for one class over (ground truth, predictions) pairs.

    Matching follows VOC: each prediction, in descending score order, is matched
    to the ground-truth box it overlaps most. If that box is already taken, or
    the overlap is under ``iou_thr``, the prediction is a false positive.

    Predictions with tied scores are treated as one rank: precision/recall points
    are only emitted between distinct scores. Otherwise a system whose scores are
    all 1.0 (the OCR and VLM baselines) would get an AP that depends on the
    arbitrary order frames happen to be listed in. The flip side: such a system
    yields ONE precision/recall point, so its AP is just recall x precision
    there, not an area under a curve. Do not rank it against a scored detector
    by AP.

    Zero-area ground truth is ignored (it can never be matched).
    """
    n_gt = sum(1 for gts, _ in frames for g in gts if g.cls == cls and g.area > 0)
    if n_gt == 0:
        return math.nan
    scored = sorted(
        ((p.score, i, p) for i, (_, preds) in enumerate(frames) for p in preds if p.cls == cls),
        key=lambda t: -t[0],
    )
    used: dict[int, set[int]] = defaultdict(set)
    points: list[tuple[float, float]] = []  # (recall, precision) at each distinct score
    tp = fp = 0
    for k, (score, i, p) in enumerate(scored):
        gts = [g for g in frames[i][0] if g.cls == cls and g.area > 0]
        overlaps = [iou(p, g) for g in gts]
        best_j = max(range(len(gts)), key=overlaps.__getitem__, default=-1)
        if best_j >= 0 and overlaps[best_j] >= iou_thr and best_j not in used[i]:
            used[i].add(best_j)
            tp += 1
        else:
            fp += 1
        last_of_tie = k == len(scored) - 1 or scored[k + 1][0] != score
        if last_of_tie:
            points.append((tp / n_gt, tp / (tp + fp)))
    # Area under the precision envelope (max precision at any recall >= r).
    ap, prev_r = 0.0, 0.0
    for k, (r, _) in enumerate(points):
        envelope = max(prec for _, prec in points[k:])
        ap += envelope * (r - prev_r)
        prev_r = r
    return ap


def detection_metrics(frames: Sequence[tuple[Sequence[Box], Sequence[Box]]]) -> dict[str, float]:
    out = {f"ap50/{c}": average_precision(frames, c) for c in CLASSES}
    present = [v for v in out.values() if not math.isnan(v)]
    out["map50"] = sum(present) / len(present) if present else math.nan
    return out


# --- operating threshold -------------------------------------------------------
def above(preds: Sequence[Box], threshold: float) -> list[Box]:
    return [p for p in preds if p.score >= threshold]


def choose_threshold(
    frames: Sequence[tuple[str, Sequence[Box], Sequence[Box]]],
    target_recall: float,
    coverage: float = DEFAULT_COVERAGE,
) -> tuple[float, float, bool]:
    """Highest confidence threshold whose region recall still meets the target.

    Returns (threshold, recall reached, whether the target was met). When no
    threshold meets it, the lowest one is returned with ``met=False`` so callers
    cannot mistake a miss for success.

    Chosen on the validation split, then applied unchanged to test, so the test
    set never influences the operating point. Expect test recall to land
    somewhat below the target: the threshold is fit to val's sample. Report the
    val-to-test drop rather than hiding it.
    """
    candidates = sorted({p.score for _, _, preds in frames for p in preds}, reverse=True)
    recall = math.nan
    for t in candidates:
        stats = [frame_stats(s, g, above(p, t), coverage) for s, g, p in frames]
        recall = privacy_metrics(stats)["region_recall"]
        if recall >= target_recall:
            return t, recall, True
    return min(candidates, default=0.0), recall, False


# --- uncertainty -------------------------------------------------------------
Metric = Callable[[Sequence[FrameStats]], float]


def _by_session(stats: Sequence[FrameStats]) -> list[list[int]]:
    groups: dict[str, list[int]] = defaultdict(list)
    for i, s in enumerate(stats):
        groups[s.session].append(i)
    return [groups[k] for k in sorted(groups)]


@dataclass(frozen=True)
class Interval:
    """A bootstrap interval and how many replicates it could not use."""

    lo: float
    hi: float
    undefined: int  # replicates where the metric was NaN (left out)
    n: int  # replicates drawn


def _percentile_ci(values: list[float], level: float) -> tuple[float, float]:
    """Percentile interval. With few sessions it under-covers, so callers report
    ``num_sessions`` next to it and the intervals are labeled approximate."""
    vals = sorted(v for v in values if not math.isnan(v))
    if not vals:
        return math.nan, math.nan
    lo_i = math.floor((1 - level) / 2 * (len(vals) - 1))
    hi_i = math.ceil((1 + level) / 2 * (len(vals) - 1))
    return vals[lo_i], vals[hi_i]


def _interval(values: list[float], level: float, max_undefined: float) -> Interval:
    undefined = sum(math.isnan(v) for v in values)
    if values and undefined / len(values) > max_undefined:
        return Interval(math.nan, math.nan, undefined, len(values))
    lo, hi = _percentile_ci(values, level)
    return Interval(lo, hi, undefined, len(values))


def bootstrap_interval(
    stats: Sequence[FrameStats],
    metric: Metric,
    n: int = 2000,
    level: float = 0.95,
    seed: int = 0,
    max_undefined: float = MAX_UNDEFINED,
) -> Interval:
    """Percentile CI from resampling whole sessions with replacement."""
    groups, rng = _by_session(stats), random.Random(seed)
    values = []
    for _ in range(n):
        sample = [stats[i] for _ in groups for i in rng.choice(groups)]
        values.append(metric(sample))
    return _interval(values, level, max_undefined)


def bootstrap_ci(
    stats: Sequence[FrameStats], metric: Metric, n: int = 2000, level: float = 0.95, seed: int = 0
) -> tuple[float, float]:
    """(lo, hi) of :func:`bootstrap_interval`."""
    iv = bootstrap_interval(stats, metric, n, level, seed)
    return iv.lo, iv.hi


def paired_bootstrap_interval(
    a: Sequence[FrameStats],
    b: Sequence[FrameStats],
    metric: Metric,
    n: int = 2000,
    level: float = 0.95,
    seed: int = 0,
    max_undefined: float = MAX_UNDEFINED,
) -> tuple[float, Interval]:
    """metric(a) - metric(b) with a CI, resampling the SAME sessions for both.

    ``a`` and ``b`` must be stats for the same frames in the same order. Pairing
    removes frame difficulty from the comparison, so a real difference shows up
    with fewer frames than two independent intervals would need. If the
    interval excludes 0, the difference is significant at that level; an
    undefined (NaN) interval is never significant.
    """
    if [s.session for s in a] != [s.session for s in b]:
        raise ValueError("paired comparison needs the same frames in the same order")
    groups, rng = _by_session(a), random.Random(seed)
    diffs = []
    for _ in range(n):
        idx = [i for _ in groups for i in rng.choice(groups)]
        diffs.append(metric([a[i] for i in idx]) - metric([b[i] for i in idx]))
    return metric(a) - metric(b), _interval(diffs, level, max_undefined)


def paired_bootstrap_diff(
    a: Sequence[FrameStats],
    b: Sequence[FrameStats],
    metric: Metric,
    n: int = 2000,
    level: float = 0.95,
    seed: int = 0,
) -> tuple[float, float, float]:
    """(diff, lo, hi) of :func:`paired_bootstrap_interval`."""
    d, iv = paired_bootstrap_interval(a, b, metric, n, level, seed)
    return d, iv.lo, iv.hi
