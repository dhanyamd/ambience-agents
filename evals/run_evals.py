"""Evaluation harness for the two-stage ambient agent.

Run:  python -m evals.run_evals

Stage 1 eval is deterministic and always runs (no LLM needed).
Stage 2 eval calls the local Ollama brain; it is skipped automatically if
Ollama is not reachable, so the harness never hard-fails on a missing model.
"""
from dataclasses import dataclass
from typing import List, Tuple

from src.funnel import is_interesting
from evals.dataset import DATASET, EvalCase


@dataclass
class Metrics:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    def add(self, predicted: bool, actual: bool) -> None:
        if predicted and actual:
            self.tp += 1
        elif predicted and not actual:
            self.fp += 1
        elif not predicted and not actual:
            self.tn += 1
        else:
            self.fn += 1

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.tn + self.fn

    @property
    def accuracy(self) -> float:
        return (self.tp + self.tn) / self.total if self.total else 0.0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 1.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def report(self, title: str) -> str:
        return (
            f"\n{title}\n"
            f"  confusion: TP={self.tp} FP={self.fp} TN={self.tn} FN={self.fn} "
            f"(n={self.total})\n"
            f"  accuracy={self.accuracy:.2f}  precision={self.precision:.2f}  "
            f"recall={self.recall:.2f}  f1={self.f1:.2f}"
        )


def eval_stage1() -> Metrics:
    """Deterministic: does the cheap filter trip on the right windows?"""
    m = Metrics()
    print("\n=== STAGE 1 · cheap filter (funnel.is_interesting) ===")
    for case in DATASET:
        predicted = is_interesting(case.stats)
        actual = case.stage1_should_trip
        m.add(predicted, actual)
        mark = "ok " if predicted == actual else "MISS"
        print(f"  [{mark}] {case.name:<22} predict_trip={predicted!s:<5} "
              f"expected={actual!s:<5} "
              f"(move={case.stats.price_move_pct:+.3f}% "
              f"imb={case.stats.imbalance:+.3f} n={case.stats.trade_count})")
    return m


def _ollama_available() -> bool:
    try:
        import requests
        from src.config import config
        r = requests.get(f"{config.ollama_host}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def eval_stage2() -> Tuple[Metrics, int, int]:
    """LLM judgment on windows that PASS Stage 1.

    Returns (metrics, json_valid_count, llm_calls). The brain only ever sees
    Stage-1 survivors in production, so we evaluate it on exactly those cases.
    """
    from src.brain import Brain  # imported lazily so Stage 1 runs without ollama installed

    brain = Brain()
    m = Metrics()
    json_valid = 0
    calls = 0
    print("\n=== STAGE 2 · brain (Ollama LLM judgment on Stage-1 survivors) ===")
    survivors: List[EvalCase] = [c for c in DATASET if c.stage1_should_trip]
    for case in survivors:
        calls += 1
        try:
            verdict = brain.analyze(case.stats)
            json_valid += 1  # got back a schema-valid, parseable verdict
        except Exception as e:  # noqa: BLE001
            print(f"  [ERR ] {case.name:<22} brain failed: {e}")
            m.add(False, case.notify_worthy)
            continue
        predicted = verdict.is_significant
        actual = case.notify_worthy
        m.add(predicted, actual)
        mark = "ok " if predicted == actual else "MISS"
        print(f"  [{mark}] {case.name:<22} notify={predicted!s:<5} "
              f"expected={actual!s:<5} sev={verdict.severity:<6} "
              f"| {verdict.headline[:48]!r}")
    return m, json_valid, calls


def main() -> None:
    s1 = eval_stage1()
    print(s1.report("STAGE 1 metrics"))

    if not _ollama_available():
        print("\n=== STAGE 2 · SKIPPED ===")
        print("  Ollama not reachable at the configured host. Start it and "
              "`ollama pull` the model to run the brain eval.")
        print("\nDone (Stage 1 only).")
        return

    s2, json_valid, calls = eval_stage2()
    print(s2.report("STAGE 2 metrics (notify-worthiness)"))
    rate = (json_valid / calls) if calls else 1.0
    print(f"  structured-output validity: {json_valid}/{calls} "
          f"valid JSON verdicts ({rate:.0%})")

    # End-to-end notification precision: of windows the agent would have pinged
    # on (passed BOTH stages), how many were genuinely worth it.
    print("\n=== END-TO-END ===")
    print(f"  notification precision (Stage 2 precision on survivors): "
          f"{s2.precision:.2f}")
    print(f"  false alarms suppressed by the brain: {s2.tn} of "
          f"{s2.tn + s2.fp} noisy survivors")
    print("\nDone.")


if __name__ == "__main__":
    main()
