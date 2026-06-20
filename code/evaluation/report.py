"""Generate the evaluation/evaluation_report.md from per-strategy results."""

from __future__ import annotations

from collections import Counter
from typing import Any

from cache import read_call_log


def _format_confusion(confusion: dict[str, Counter]) -> str:
    if not confusion:
        return "_No data_"
    labels = sorted(set(confusion.keys()) | {p for c in confusion.values() for p in c.keys()})
    lines = [
        "| actual \\ predicted | " + " | ".join(labels) + " |",
        "|" + "|".join(["---"] * (len(labels) + 1)) + "|",
    ]
    for actual in labels:
        row = confusion.get(actual, Counter())
        cells = [str(row.get(predicted, 0)) for predicted in labels]
        lines.append(f"| **{actual}** | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _summarize_call_log(call_log: list[dict], strategy: str) -> dict[str, Any]:
    relevant = [e for e in call_log if e.get("strategy") == strategy]
    total_calls = len([e for e in relevant if not e.get("cached")])
    cached_calls = len([e for e in relevant if e.get("cached")])
    errors = [e for e in relevant if e.get("error")]
    total_prompt_tokens = sum(int(e.get("prompt_tokens", 0)) for e in relevant)
    total_completion_tokens = sum(int(e.get("completion_tokens", 0)) for e in relevant)
    elapsed_ms = [int(e.get("elapsed_ms", 0)) for e in relevant if int(e.get("elapsed_ms", 0)) > 0]

    nodes = Counter(e.get("node", "unknown") for e in relevant)
    models = Counter(e.get("model", "unknown") for e in relevant)

    return {
        "total_calls": total_calls,
        "cached_calls": cached_calls,
        "errors": len(errors),
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_tokens": total_prompt_tokens + total_completion_tokens,
        "p50_latency_ms": sorted(elapsed_ms)[len(elapsed_ms) // 2] if elapsed_ms else 0,
        "p95_latency_ms": (sorted(elapsed_ms)[int(len(elapsed_ms) * 0.95)] if elapsed_ms else 0),
        "nodes": dict(nodes),
        "models": dict(models),
    }


def build_report(
    strategy1_results: dict,
    strategy2_results: dict,
    strategy3_results: dict | None = None,
    strategy1_name: str = "m3_only",
    strategy2_name: str = "m3_text_nemotron_vision",
    strategy3_name: str = "m3_nemotron_ensemble",
) -> str:
    """Build the full markdown evaluation report."""
    log = read_call_log()
    s1_ops = _summarize_call_log(log, strategy1_name)
    s2_ops = _summarize_call_log(log, strategy2_name)
    s3_ops = _summarize_call_log(log, strategy3_name) if strategy3_results else None

    candidates = [
        (strategy1_name, strategy1_results),
        (strategy2_name, strategy2_results),
    ]
    if strategy3_results:
        candidates.append((strategy3_name, strategy3_results))
    winner_name, winner_results = max(candidates, key=lambda x: x[1]["weighted_score"])

    sections: list[str] = []
    sections.append("# Evaluation Report\n")
    sections.append(f"_Generated: {__import__('datetime').datetime.now().isoformat()}_\n")

    sections.append("## Summary\n")
    sections.append(
        f"- **Winning strategy:** `{winner_name}` (weighted score {winner_results['weighted_score']:.1%})"
    )
    sections.append(
        f"- **Rows evaluated:** {strategy1_results['matched_rows']} (sample_claims.csv)"
    )
    sections.append("")

    sections.append("## Strategy 1: `m3_only` (M3 does text + vision)\n")
    _add_strategy_section(sections, strategy1_results, s1_ops)

    sections.append("\n## Strategy 2: `m3_text_nemotron_vision` (M3 text + Nemotron Omni vision)\n")
    _add_strategy_section(sections, strategy2_results, s2_ops)

    if strategy3_results:
        sections.append("\n## Strategy 3: `m3_nemotron_ensemble` (M3 + Nemotron reconciled)\n")
        _add_strategy_section(sections, strategy3_results, s3_ops)

    sections.append("\n## Operational Analysis\n")
    header_cols = ["Strategy 1 (m3_only)", "Strategy 2 (m3_text+omni)"]
    if strategy3_results:
        header_cols.append("Strategy 3 (ensemble)")
    sections.append("| Metric | " + " | ".join(header_cols) + " |")
    sections.append("|" + "|".join(["---"] * (len(header_cols) + 1)) + "|")
    s_cells = [s1_ops, s2_ops]
    if strategy3_results:
        s_cells.append(s3_ops)
    for metric in ["total_calls", "cached_calls", "errors", "total_prompt_tokens", "total_completion_tokens", "total_tokens", "p50_latency_ms", "p95_latency_ms"]:
        key = metric
        vals = [str(c[key]) for c in s_cells]
        sections.append(f"| {metric} | " + " | ".join(vals) + " |")
    sections.append("")

    sections.append("\n### Models Used\n")
    sections.append(f"- Strategy 1: {s1_ops['models']}")
    sections.append(f"- Strategy 2: {s2_ops['models']}")
    if strategy3_results:
        sections.append(f"- Strategy 3: {s3_ops['models']}")
    sections.append("")

    sections.append("\n### Node Distribution\n")
    sections.append(f"- Strategy 1: {s1_ops['nodes']}")
    sections.append(f"- Strategy 2: {s2_ops['nodes']}")
    if strategy3_results:
        sections.append(f"- Strategy 3: {s3_ops['nodes']}")
    sections.append("")

    sections.append("\n## Cost & Quota Notes\n")
    sections.append(
        "- **Token Router (M3):** unlimited quota per user (confirmed). No per-call cost in this run."
    )
    sections.append(
        "- **NVIDIA NIM (Nemotron Omni):** free tier, ~40 RPM. We use Semaphore(1) + 1.6s sleep + tenacity retry."
    )
    sections.append(
        "- **Caching:** vision calls are cached by sha256(image) + model + prompt_version + vote round."
    )
    sections.append(
        "- **TPM awareness:** both providers return usage; we log it. NIM may have TPM caps in addition to RPM."
    )
    sections.append("")

    sections.append("\n## Recommended Configuration for test set\n")
    sections.append(
        f"Use **`{winner_name}`** for the final `output.csv` generation on `dataset/claims.csv`."
    )
    sections.append("")

    return "\n".join(sections)


def _add_strategy_section(sections: list[str], results: dict, ops: dict) -> None:
    sections.append(f"- Weighted score: **{results['weighted_score']:.1%}**")
    sections.append(f"- Matched rows: {results['matched_rows']}")
    sections.append("")
    sections.append("### Per-column accuracy")
    sections.append("| Column | Accuracy |")
    sections.append("|---|---|")
    for col, acc in results["per_column_accuracy"].items():
        if col in {"user_id", "image_paths", "user_claim", "claim_object"}:
            continue
        correct = results["per_column_correct"].get(col, 0)
        total = results["per_column_total"].get(col, 0)
        sections.append(f"| {col} | {acc:.1%} ({correct}/{total}) |")
    sections.append("")
    sections.append("### Claim status confusion matrix")
    sections.append(_format_confusion(results["confusion_matrix"]))
    sections.append("")
