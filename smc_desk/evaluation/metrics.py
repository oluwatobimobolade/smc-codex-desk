from datetime import datetime
from decimal import Decimal
from typing import Any, List, Dict, Tuple
from collections import defaultdict
from pydantic import BaseModel

from smc_desk.perception.ontology import SMCObject
from smc_desk.evaluation.gold_set import GoldSetCase, GoldSetLabel


class ObjectMatchResult(BaseModel):
    object_type: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    
    @property
    def precision(self) -> float:
        if self.true_positives + self.false_positives == 0:
            return 0.0
        return self.true_positives / (self.true_positives + self.false_positives)
        
    @property
    def recall(self) -> float:
        if self.true_positives + self.false_negatives == 0:
            return 0.0
        return self.true_positives / (self.true_positives + self.false_negatives)
        
    @property
    def f1_score(self) -> float:
        p = self.precision
        r = self.recall
        if p + r == 0:
            return 0.0
        return 2 * (p * r) / (p + r)


def _get_field(obj: Any, *names: str) -> Any:
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _label_evidence(label: GoldSetLabel) -> dict:
    return label.ground_truth_evidence or {}


def _object_type(item: Any) -> str:
    if isinstance(item, GoldSetLabel):
        return item.object_type
    return str(_get_field(item, "object_type") or "generic")


def _direction(item: Any) -> str | None:
    if isinstance(item, GoldSetLabel):
        value = _get_field(_label_evidence(item), "direction")
    else:
        value = _get_field(item, "direction")
    return getattr(value, "value", value)


def _event_time(item: Any) -> datetime | None:
    if isinstance(item, GoldSetLabel):
        evidence = _label_evidence(item)
        return _parse_time(_get_field(evidence, "pivot_time", "timestamp", "event_time", "confirmed_at"))
    return _parse_time(_get_field(item, "pivot_time", "timestamp", "confirmed_at"))


def _price_interval(item: Any) -> tuple[float, float] | None:
    if isinstance(item, GoldSetLabel):
        source = _label_evidence(item)
    else:
        source = item

    low = _get_field(source, "price_low", "low", "zone_low")
    high = _get_field(source, "price_high", "high", "zone_high")
    point = _get_field(source, "price", "level", "broken_price")

    if low is None and high is None and point is not None:
        low = high = point
    if low is None or high is None:
        return None

    lo = float(Decimal(str(low)))
    hi = float(Decimal(str(high)))
    return (min(lo, hi), max(lo, hi))


def _interval_iou(a: tuple[float, float], b: tuple[float, float]) -> float:
    left = max(a[0], b[0])
    right = min(a[1], b[1])
    intersection = max(0.0, right - left)
    union = max(a[1], b[1]) - min(a[0], b[0])
    if union <= 0:
        return 1.0 if abs(a[0] - b[0]) <= max(abs(a[0]), 1.0) * 0.001 else 0.0
    return intersection / union


def _prices_match(
    prediction: Any,
    label: GoldSetLabel,
    price_tolerance_bps: float,
    zone_iou_threshold: float,
) -> bool:
    pred_interval = _price_interval(prediction)
    gold_interval = _price_interval(label)
    if pred_interval is None or gold_interval is None:
        return False

    pred_is_point = abs(pred_interval[1] - pred_interval[0]) <= 1e-12
    gold_is_point = abs(gold_interval[1] - gold_interval[0]) <= 1e-12
    tolerance_ratio = price_tolerance_bps / 10000.0

    if pred_is_point and gold_is_point:
        anchor = max(abs(gold_interval[0]), 1e-9)
        return abs(pred_interval[0] - gold_interval[0]) / anchor <= tolerance_ratio

    if pred_is_point:
        tolerance = max(abs(pred_interval[0]), 1e-9) * tolerance_ratio
        return gold_interval[0] - tolerance <= pred_interval[0] <= gold_interval[1] + tolerance

    if gold_is_point:
        tolerance = max(abs(gold_interval[0]), 1e-9) * tolerance_ratio
        return pred_interval[0] - tolerance <= gold_interval[0] <= pred_interval[1] + tolerance

    return _interval_iou(pred_interval, gold_interval) >= zone_iou_threshold


def _objects_match(
    prediction: SMCObject,
    label: GoldSetLabel,
    time_tolerance_bars: int,
    price_tolerance_bps: float,
    zone_iou_threshold: float,
) -> bool:
    if _object_type(prediction) != _object_type(label):
        return False

    pred_direction = _direction(prediction)
    gold_direction = _direction(label)
    if pred_direction and gold_direction and pred_direction != gold_direction:
        return False

    pred_time = _event_time(prediction)
    gold_time = _event_time(label)
    if pred_time is not None and gold_time is not None:
        # The evaluator does not know the case timeframe here; for 15m cases,
        # one bar is 900 seconds. Wider bars should provide explicit bar_index
        # in ground_truth_evidence and use a larger tolerance if needed.
        tolerance_seconds = time_tolerance_bars * 900
        if abs((pred_time - gold_time).total_seconds()) > tolerance_seconds:
            return False

    return _prices_match(prediction, label, price_tolerance_bps, zone_iou_threshold)


def match_objects(
    predictions: List[SMCObject],
    gold_labels: List[GoldSetLabel],
    time_tolerance_bars: int = 1,
    price_tolerance_bps: float = 10.0,
    zone_iou_threshold: float = 0.5,
) -> ObjectMatchResult:
    """
    Match engine predictions against gold labels to compute precision/recall.
    Matching logic varies by object type, but generally requires temporal and spatial overlap.
    """
    object_type = _object_type(predictions[0]) if predictions else _object_type(gold_labels[0]) if gold_labels else "generic"
    result = ObjectMatchResult(object_type=object_type)
    matched_gold: set[int] = set()

    for prediction in predictions:
        best_idx: int | None = None
        for idx, label in enumerate(gold_labels):
            if idx in matched_gold:
                continue
            if _objects_match(prediction, label, time_tolerance_bars, price_tolerance_bps, zone_iou_threshold):
                best_idx = idx
                break
        if best_idx is None:
            result.false_positives += 1
        else:
            matched_gold.add(best_idx)
            result.true_positives += 1

    result.false_negatives = len(gold_labels) - len(matched_gold)
    return result

def evaluate_case(predictions: List[SMCObject], case: GoldSetCase) -> Dict[str, ObjectMatchResult]:
    """Evaluates all object types for a single case."""
    results_by_type = {}
    
    # Group predictions and labels by type
    preds_by_type = defaultdict(list)
    for p in predictions:
        preds_by_type[p.object_type].append(p)
        
    labels_by_type = defaultdict(list)
    for label in case.labels:
        if label.agreed_status == "confirmed":
            labels_by_type[label.object_type].append(label)
            
    # For each object type defined in the ontology, compute metrics
    for obj_type in set(preds_by_type.keys()).union(labels_by_type.keys()):
        results_by_type[obj_type] = match_objects(
            preds_by_type[obj_type],
            labels_by_type[obj_type]
        )
        
    return results_by_type
