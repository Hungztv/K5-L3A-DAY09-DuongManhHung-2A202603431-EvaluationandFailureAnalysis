"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def _ratchet_problems(spec: dict, base_spec: dict) -> list[str]:
    problems: list[str] = []
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return problems

    spec_metrics = {m["id"]: m for m in spec.get("metrics") or []}
    for bm in base_spec.get("metrics") or []:
        mid = bm["id"]
        if mid not in spec_metrics:
            problems.append(f"ratchet: metric {mid} removed")
            continue
        sm = spec_metrics[mid]
        if bm.get("blocking") and not sm.get("blocking"):
            problems.append(f"ratchet: metric {mid} became non-blocking")
        bth = bm.get("threshold") or {}
        sth = sm.get("threshold") or {}
        if "max" in bth and ("max" not in sth or sth["max"] > bth["max"]):
            problems.append(f"ratchet: metric {mid} max loosened ({bth['max']} -> {sth.get('max')})")
        if "min" in bth and ("min" not in sth or sth["min"] < bth["min"]):
            problems.append(f"ratchet: metric {mid} min loosened ({bth['min']} -> {sth.get('min')})")
        if "max_increase" in bth and ("max_increase" not in sth or sth["max_increase"] > bth["max_increase"]):
            problems.append(f"ratchet: metric {mid} max_increase loosened")
        if bth.get("no_significant_drop") and not sth.get("no_significant_drop"):
            problems.append(f"ratchet: metric {mid} dropped no_significant_drop")

    spec_slices = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for bsl in base_spec.get("slices") or []:
        key = (bsl["name"], bsl["metric"])
        if key not in spec_slices:
            problems.append(f"ratchet: slice {bsl['name']}/{bsl['metric']} removed")
            continue
        ssl = spec_slices[key]
        if bsl.get("blocking") and not ssl.get("blocking"):
            problems.append(f"ratchet: slice {bsl['name']}/{bsl['metric']} became non-blocking")
        if "min" in bsl and ("min" not in ssl or ssl["min"] < bsl["min"]):
            problems.append(f"ratchet: slice {bsl['name']}/{bsl['metric']} min loosened")
        if "max" in bsl and ("max" not in ssl or ssl["max"] > bsl["max"]):
            problems.append(f"ratchet: slice {bsl['name']}/{bsl['metric']} max loosened")
        if bsl.get("no_significant_drop") and not ssl.get("no_significant_drop"):
            problems.append(f"ratchet: slice {bsl['name']}/{bsl['metric']} dropped no_significant_drop")

    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate."""
    problems: list[str] = []

    if pr.get("evaluator_failures"):
        problems.append(f"evaluator_failures non-empty ({len(pr['evaluator_failures'])})")

    pr_metrics = pr.get("metrics") or {}
    for k, v in pr_metrics.items():
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            problems.append(f"metric {k} is non-finite ({v})")
        elif v is None and k != "cost_per_success":
            problems.append(f"metric {k} is None")

    pr_manifest = pr.get("manifest") or {}
    base_manifest = base.get("manifest") or {}
    pr_rows = pr.get("rows") or []
    base_rows = base.get("rows") or []

    expected_len = int(pr_manifest.get("items") or 0) * len(pr_manifest.get("seeds") or [])
    if len(pr_rows) != expected_len:
        problems.append(f"row count {len(pr_rows)} != manifest {expected_len}")

    pr_pairs = [(r.get("item_id"), r.get("seed")) for r in pr_rows]
    base_pairs = [(r.get("item_id"), r.get("seed")) for r in base_rows]
    if len(pr_pairs) != len(set(pr_pairs)):
        problems.append("duplicate (item_id, seed) rows in PR")
    if set(pr_pairs) != set(base_pairs):
        problems.append("PR (item_id, seed) set differs from baseline")

    row_metrics = {m["id"] for m in spec.get("metrics") or [] if m["id"] in GRADERS}
    if base_rows:
        row_metrics |= {m["id"] for m in spec.get("metrics") or [] if m["id"] in base_rows[0]}

    for r in pr_rows:
        for mid in sorted(row_metrics):
            val = r.get(mid)
            if val is None or (isinstance(val, float) and not math.isfinite(val)):
                problems.append(f"row {r.get('item_id')}@{r.get('seed')} missing/non-finite {mid}")
                break

    if pr_rows:
        for mid in sorted(row_metrics):
            if mid in pr_metrics and isinstance(pr_metrics[mid], (int, float)) and math.isfinite(pr_metrics[mid]):
                vals = [r.get(mid) for r in pr_rows]
                if all(v is not None for v in vals):
                    if mid in ("secret_leak", "approval_bypass"):
                        expected_val = sum(bool(v) for v in vals)
                    else:
                        expected_val = round(sum(bool(v) for v in vals) / len(vals), 4)
                    if abs(float(pr_metrics[mid]) - float(expected_val)) > 1e-3:
                        problems.append(f"metric {mid}={pr_metrics[mid]} disagrees with rows ({expected_val})")

    base_slices: dict[str, list[str]] = {}
    for r in base_rows:
        base_slices.setdefault(r["item_id"], sorted(set(r.get("slices") or [])))
    for r in pr_rows:
        iid = r.get("item_id")
        if iid in base_slices and sorted(set(r.get("slices") or [])) != base_slices[iid]:
            problems.append(f"slice tags modified for {iid}")
            break

    if base_spec is not None:
        problems.extend(_ratchet_problems(spec, base_spec))

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, mid = s["name"], s["metric"]
        a = per_item(pr, mid, slice_name=name)
        b = per_item(base, mid, slice_name=name)
        val = (sum(a.values()) / len(a)) if a else None
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        else:
            if "min" in s and val < s["min"]:
                verdict = "fail"
            if "max" in s and val > s["max"]:
                verdict = "fail"
            if s.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap(
                        [a[k] for k in keys],
                        [b[k] for k in keys],
                        n_resamples=bs.get("n_resamples", 1000),
                        rng=bs.get("rng", 2027),
                        confidence=bs.get("confidence", 0.95),
                    )
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                    if hi < 0:
                        verdict = "fail"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(f"slice:{name}/{mid}")
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        val_str = f"{val:.4f}" if isinstance(val, float) else str(val)
        th = {k: s[k] for k in ("min", "max", "no_significant_drop") if k in s}
        lines.append(f"  slice:{name}/{mid:<14} {val_str:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
