"""
Human Challenge Evaluator — Double-Blind Evaluation Engine.

Computes:
- Jaccard consistency (human-to-human agreement)
- AI accuracy vs. human consensus
- AI calibration error
- Per-primitive agreement rates
- Precision, Recall, F1 for AI vs consensus
"""
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any


class HumanChallengeEvaluator:
    def __init__(self, time_tolerance_sec: float = 900.0, price_tolerance_pct: float = 0.001):
        self.time_tolerance_sec = time_tolerance_sec
        self.price_tolerance_pct = price_tolerance_pct

    @staticmethod
    def _nested_get(annotation: Dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in annotation:
                return annotation[key]
        evidence = annotation.get("ground_truth_evidence")
        if isinstance(evidence, dict):
            for key in keys:
                if key in evidence:
                    return evidence[key]
        return None

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    @classmethod
    def _price_interval(cls, annotation: Dict[str, Any]) -> tuple[float, float] | None:
        low = cls._nested_get(annotation, "price_low", "low", "zone_low")
        high = cls._nested_get(annotation, "price_high", "high", "zone_high")
        point = cls._nested_get(annotation, "price", "level", "broken_price")

        if low is None and high is None and point is not None:
            low = high = point
        if low is None or high is None:
            return None

        lo = float(low)
        hi = float(high)
        return (min(lo, hi), max(lo, hi))

    @staticmethod
    def _interval_iou(a: tuple[float, float], b: tuple[float, float]) -> float:
        left = max(a[0], b[0])
        right = min(a[1], b[1])
        intersection = max(0.0, right - left)
        union = max(a[1], b[1]) - min(a[0], b[0])
        if union <= 0:
            return 1.0 if abs(a[0] - b[0]) <= max(abs(a[0]), 1.0) * 0.001 else 0.0
        return intersection / union

    def _is_match(
        self,
        a: Dict[str, Any],
        b: Dict[str, Any],
        time_tolerance_sec: float | None = None,
        price_tolerance_pct: float | None = None,
        zone_iou_threshold: float = 0.5,
    ) -> bool:
        """Match two annotations by primitive, direction, timestamp proximity, and price proximity."""
        time_tolerance_sec = self.time_tolerance_sec if time_tolerance_sec is None else time_tolerance_sec
        price_tolerance_pct = self.price_tolerance_pct if price_tolerance_pct is None else price_tolerance_pct

        primitive_a = self._nested_get(a, "primitive", "object_type")
        primitive_b = self._nested_get(b, "primitive", "object_type")
        direction_a = self._nested_get(a, "direction")
        direction_b = self._nested_get(b, "direction")
        if primitive_a != primitive_b:
            return False
        if direction_a is not None and direction_b is not None and direction_a != direction_b:
            return False

        # Check timestamp
        t_a = self._parse_timestamp(self._nested_get(a, "timestamp", "pivot_time", "event_time", "confirmed_at"))
        t_b = self._parse_timestamp(self._nested_get(b, "timestamp", "pivot_time", "event_time", "confirmed_at"))
        if t_a is not None and t_b is not None:
            if abs((t_a - t_b).total_seconds()) > time_tolerance_sec:
                return False
        elif t_a is not None or t_b is not None:
            return False

        # Check price
        interval_a = self._price_interval(a)
        interval_b = self._price_interval(b)
        if interval_a is None or interval_b is None:
            return False

        a_is_point = abs(interval_a[1] - interval_a[0]) <= 1e-12
        b_is_point = abs(interval_b[1] - interval_b[0]) <= 1e-12
        if a_is_point and b_is_point:
            if abs(interval_a[0] - interval_b[0]) / max(abs(interval_a[0]), 1e-8) > price_tolerance_pct:
                return False
        elif a_is_point:
            tolerance = max(abs(interval_a[0]), 1e-8) * price_tolerance_pct
            if not (interval_b[0] - tolerance <= interval_a[0] <= interval_b[1] + tolerance):
                return False
        elif b_is_point:
            tolerance = max(abs(interval_b[0]), 1e-8) * price_tolerance_pct
            if not (interval_a[0] - tolerance <= interval_b[0] <= interval_a[1] + tolerance):
                return False
        elif self._interval_iou(interval_a, interval_b) < zone_iou_threshold:
            return False

        return True

    def _pairwise_matches(
        self,
        annos_a: list[dict[str, Any]],
        annos_b: list[dict[str, Any]],
    ) -> tuple[int, dict[str, dict[str, int]]]:
        matched_b: set[int] = set()
        per_primitive: dict[str, dict[str, int]] = defaultdict(lambda: {"matched": 0, "total_a": 0, "total_b": 0})
        for a in annos_a:
            per_primitive[self._nested_get(a, "primitive", "object_type")]["total_a"] += 1
        for b in annos_b:
            per_primitive[self._nested_get(b, "primitive", "object_type")]["total_b"] += 1

        matches = 0
        for a in annos_a:
            for idx, b in enumerate(annos_b):
                if idx in matched_b:
                    continue
                if self._is_match(a, b):
                    matched_b.add(idx)
                    matches += 1
                    per_primitive[self._nested_get(a, "primitive", "object_type")]["matched"] += 1
                    break
        return matches, per_primitive

    def _build_consensus(
        self,
        cases: list[dict[str, Any]],
        reviewer_case_annos: dict[str, dict[str, list[dict[str, Any]]]],
        reviewer_ids: list[str],
    ) -> list[dict[str, Any]]:
        if len(reviewer_ids) < 2:
            return []

        consensus: list[dict[str, Any]] = []
        seen: set[tuple[str, str, int]] = set()
        for case in cases:
            case_id = case.get("case_id")
            for reviewer_id in reviewer_ids:
                annos = reviewer_case_annos.get(reviewer_id, {}).get(case_id, [])
                for idx, anno in enumerate(annos):
                    ref = (str(case_id), reviewer_id, idx)
                    if ref in seen:
                        continue
                    cluster = [ref]
                    reviewers = {reviewer_id}
                    for other_id in reviewer_ids:
                        if other_id == reviewer_id:
                            continue
                        for other_idx, other in enumerate(reviewer_case_annos.get(other_id, {}).get(case_id, [])):
                            other_ref = (str(case_id), other_id, other_idx)
                            if other_ref in seen:
                                continue
                            if self._is_match(anno, other):
                                cluster.append(other_ref)
                                reviewers.add(other_id)
                                break
                    if len(reviewers) >= 2:
                        consensus.append(anno)
                        seen.update(cluster)
        return consensus

    def run_blind_challenge(
        self,
        cases: List[Dict[str, Any]],
        human_annotations: Dict[str, List[Dict[str, Any]]],  # reviewer -> annotations
        ai_annotations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Blinds the labels from human reviewers and AI systems, matches them,
        and computes accuracy, consistency, and calibration.
        """
        # Blind the reviewer names to maintain double-blind integrity
        blind_keys = sorted(human_annotations.keys())
        blinded_reviewers = [f"Reviewer_{i}" for i in range(len(blind_keys))]

        # Group human annotations by case
        reviewer_case_annos = {}
        for rev_id, annos in human_annotations.items():
            reviewer_case_annos[rev_id] = {}
            for anno in annos:
                case_id = anno.get("case_id")
                if case_id not in reviewer_case_annos[rev_id]:
                    reviewer_case_annos[rev_id][case_id] = []
                reviewer_case_annos[rev_id][case_id].append(anno)

        # Group AI annotations by case
        ai_case_annos = {}
        for anno in ai_annotations:
            case_id = anno.get("case_id")
            if case_id not in ai_case_annos:
                ai_case_annos[case_id] = []
            ai_case_annos[case_id].append(anno)

        consensus_labels = self._build_consensus(cases, reviewer_case_annos, blind_keys)
        per_primitive_stats = defaultdict(lambda: {"matched": 0, "total_a": 0, "total_b": 0})
        
        # Calculate human-to-human consistency over all reviewer pairs.
        if len(blind_keys) >= 2:
            pair_scores = []
            for left_idx, rev_a in enumerate(blind_keys):
                for rev_b in blind_keys[left_idx + 1:]:
                    total_annos_a = 0
                    total_annos_b = 0
                    pair_matches = 0
                    for case in cases:
                        case_id = case.get("case_id")
                        annos_a = reviewer_case_annos.get(rev_a, {}).get(case_id, [])
                        annos_b = reviewer_case_annos.get(rev_b, {}).get(case_id, [])
                        total_annos_a += len(annos_a)
                        total_annos_b += len(annos_b)
                        matches, prim_stats = self._pairwise_matches(annos_a, annos_b)
                        pair_matches += matches
                        for primitive, stats in prim_stats.items():
                            per_primitive_stats[primitive]["matched"] += stats["matched"]
                            per_primitive_stats[primitive]["total_a"] += stats["total_a"]
                            per_primitive_stats[primitive]["total_b"] += stats["total_b"]

                    denominator = total_annos_a + total_annos_b - pair_matches
                    if denominator > 0:
                        pair_scores.append(pair_matches / denominator)
            consistency_jaccard = (sum(pair_scores) / len(pair_scores)) if pair_scores else None
        else:
            consistency_jaccard = None

        # Now score AI annotations against the consensus labels
        tp = 0
        matched_consensus = set()
        calibration_errors = []
        
        for ai_anno in ai_annotations:
            # Match AI annotation to consensus
            matched = False
            for idx, gold in enumerate(consensus_labels):
                if idx not in matched_consensus and self._is_match(ai_anno, gold):
                    matched_consensus.add(idx)
                    tp += 1
                    matched = True
                    break

            # Check calibration if confidence is provided
            confidence = ai_anno.get("confidence", 1.0)
            correctness = 1.0 if matched else 0.0
            calibration_errors.append(abs(confidence - correctness))

        fp = len(ai_annotations) - tp
        fn = len(consensus_labels) - tp
        
        # Jaccard (IoU) for AI vs consensus. Empty evidence is not accuracy.
        has_ai_evaluation_basis = bool(consensus_labels or ai_annotations)
        if has_ai_evaluation_basis:
            ai_jaccard = (tp / (tp + fp + fn)) if (tp + fp + fn) > 0 else None
            precision = (tp / (tp + fp)) if (tp + fp) > 0 else None
            recall = (tp / (tp + fn)) if (tp + fn) > 0 else None
            f1 = (2 * precision * recall / (precision + recall)) if precision is not None and recall is not None and (precision + recall) > 0 else 0.0
        else:
            ai_jaccard = None
            precision = None
            recall = None
            f1 = None

        ai_calibration_error = (sum(calibration_errors) / len(calibration_errors)) if calibration_errors else 0.0

        # Per-primitive agreement summary
        primitive_agreement = {}
        for prim, stats in per_primitive_stats.items():
            total = stats["total_a"] + stats["total_b"]
            denom = total - stats["matched"]
            primitive_agreement[prim] = {
                "jaccard": round(stats["matched"] / denom, 4) if denom > 0 else 1.0,
                "matched": stats["matched"],
                "total_a": stats["total_a"],
                "total_b": stats["total_b"],
            }

        return {
            "blinded_reviewers": blinded_reviewers,
            "consistency_jaccard": round(consistency_jaccard, 4) if consistency_jaccard is not None else None,
            "total_cases_evaluated": len(cases),
            "consensus_label_count": len(consensus_labels),
            "ai_evaluation_status": "scored" if has_ai_evaluation_basis and consensus_labels else "insufficient_consensus",
            "ai_jaccard_vs_consensus": round(ai_jaccard, 4) if ai_jaccard is not None else None,
            "ai_precision": round(precision, 4) if precision is not None else None,
            "ai_recall": round(recall, 4) if recall is not None else None,
            "ai_f1": round(f1, 4) if f1 is not None else None,
            "ai_calibration_error": round(ai_calibration_error, 4),
            "per_primitive_agreement": primitive_agreement,
        }
