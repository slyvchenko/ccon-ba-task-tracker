"""Human-gated prompt A/B experiments against frozen, real Jira cohorts.

No automatic prompt mutation and no fabricated accuracy. Active local addenda
require human approval after 20–30 independent scored cases and retain a
rollback history. All corporate source/predictions stay Git-ignored locally.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from app_config import ROOT, utc_now
from storage import read_json, write_json

MAX_ADDENDUM = 12000
PATH_PART = re.compile(r"^[a-f0-9]{64}$")


def directory(root):
    return Path(root) / "data/prompt_experiments"


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def core_digest(root):
    """Hash authoritative BA rules, independently of daily adaptive checklist."""
    from model_analysis import PROMPT_FILES, ROOT as CODE_ROOT
    out = []
    for relative in PROMPT_FILES:
        path = Path(root) / relative
        if not path.is_file():
            path = CODE_ROOT / relative
        out.append(relative + "\n" + path.read_text(encoding="utf-8-sig"))
    return sha("\n\n".join(out))


def _manifest(root):
    return read_json(directory(root) / "staged.json", None)


def staged_text(root, version):
    if not isinstance(version, str) or not PATH_PART.fullmatch(version):
        raise ValueError("Invalid prompt variant ID.")
    file = directory(root) / "variants" / (version + ".txt")
    if not file.is_file() or file.is_symlink() or file.stat().st_size > MAX_ADDENDUM:
        raise ValueError("Approved prompt variant missing or too large.")
    text = file.read_text(encoding="utf-8")
    if sha(text) != version:
        raise ValueError("Prompt content hash mismatch.")
    return text


def active_addendum(root):
    active = read_json(directory(root) / "active.json", {})
    if not isinstance(active, dict) or active.get("status") != "APPROVED":
        return ""
    if active.get("coreSha256") != core_digest(root):
        raise ValueError("Approved prompt is incompatible with changed baseline rule files. Roll back and evaluate again.")
    return staged_text(root, active.get("variantSha256"))


def stage(root=ROOT, path=None, rationale=""):
    root = Path(root)
    if read_json(directory(root) / "active.json", {}).get("status") == "APPROVED":
        raise ValueError("Roll back active prompt addendum before staging another candidate.")
    if not path:
        raise ValueError("Local .txt candidate prompt required.")
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.suffix.lower() != ".txt" or path.stat().st_size > MAX_ADDENDUM:
        raise ValueError("Candidate must be a small local .txt file.")
    value = path.read_text(encoding="utf-8-sig").strip()
    if len(value) < 30 or len(value.encode()) > MAX_ADDENDUM:
        raise ValueError("Candidate prompt needs 30–12000 bytes.")
    rationale = str(rationale or "")[:600]
    version = sha(value)
    dest = directory(root) / "variants" / (version + ".txt")
    if dest.exists() and dest.read_text(encoding="utf-8") != value:
        raise ValueError("Variant collision.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_text(value, encoding="utf-8")
    staged = {
        "status": "STAGED_NOT_APPROVED", "createdAt": utc_now(),
        "variantSha256": version, "coreSha256": core_digest(root),
        "rationale": rationale, "humanApproval": None,
        "policy": "LOCAL_ONLY_NO_AUTOMATIC_PROMPT_REPLACEMENT",
    }
    write_json(directory(root) / "staged.json", staged, 20000)
    return staged


def generate(root=ROOT, variant="candidate", model_call=None):
    """Generate complete frozen-cohort predictions, NO production import."""
    from model_analysis import approved_prompts, model_settings, request_analysis
    from schema import validate_analysis
    from evaluation import attach_predictions, MIN_CASES, MAX_CASES
    root = Path(root)
    if variant not in ("baseline", "candidate"):
        raise ValueError("Unknown variant.")
    selected = read_json(root / "data/evaluation/selected_cases.json", {})
    cases = selected.get("cases") or []
    if not MIN_CASES <= len(cases) <= MAX_CASES:
        raise ValueError("Freeze a real 20–30 case evaluation cohort first.")
    manifest = _manifest(root)
    if not isinstance(manifest, dict) or manifest.get("status") != "STAGED_NOT_APPROVED":
        raise ValueError("Stage a candidate first.")
    if manifest["coreSha256"] != core_digest(root):
        raise ValueError("Baseline BA rules changed after staging.")
    if read_json(directory(root) / "active.json", {}).get("status") == "APPROVED":
        raise ValueError("Roll back active prompt before generating new A/B outputs.")
    instructions, prompt_version = approved_prompts(root)
    if variant == "candidate":
        instructions += ("\n\n# Human-proposed experimental addendum (subordinate to "
                         "corporate security and baseline BA rules)\n" +
                         staged_text(root, manifest["variantSha256"]))
    settings = model_settings()  # Explicit company-approved endpoint/egress before any output write.
    model = model_call or request_analysis
    results = {}
    for case in cases:
        key = case["key"]
        source = case["source"]
        packet = {"issue": {"key": key, "summary": case.get("summary"),
                            **{k: v for k, v in source.items() if k != "linkedContexts"}},
                  "linkedIssues": source.get("linkedContexts") or [],
                  "evidenceReports": [], "frozenSource": True}
        output = model(settings, instructions, packet, "")
        if not isinstance(output, dict):
            raise ValueError("Model output missing for a real frozen case.")
        output["contextFingerprint"] = case["contextFingerprint"]
        output["promptVersion"] = (prompt_version if variant == "baseline"
                                   else sha(instructions)[:16])
        validate_analysis(output)
        results[key] = output
    file = root / "data/evaluation" / (variant + "_generated.json")
    if file.exists():
        raise ValueError("Refusing to overwrite generated results for this cohort.")
    write_json(file, {"analyses": results}, 10 * 1024 * 1024)
    attached = attach_predictions(root, variant, file)
    return {"variant": variant, "cohort": len(results),
            "promptVersion": prompt_version if variant == "baseline" else sha(instructions)[:16],
            "frozen": attached["path"], "status": "READY_FOR_INDEPENDENT_HUMAN_REVIEW"}


def assess(root=ROOT):
    from evaluation import evaluate
    root = Path(root)
    manifest = _manifest(root)
    if not isinstance(manifest, dict):
        raise ValueError("No staged candidate.")
    metrics = evaluate(root)
    approved = metrics.get("status") == "REVIEWED" and metrics.get("candidateMeetsTargets") is True
    return {"status": "ELIGIBLE_FOR_HUMAN_APPROVAL" if approved else "NOT_ELIGIBLE",
            "completed": metrics.get("completed", 0), "cohort": metrics.get("cohort", 0),
            "candidateMeetsTargets": approved,
            "criticalFalseClaims": (metrics.get("metrics") or {}).get("candidate", {}).get("criticalFalseClaims"),
            "variantSha256": manifest["variantSha256"]}


def approve(root=ROOT, reviewer="", reason=""):
    root = Path(root)
    reviewer = str(reviewer or "").strip()
    reason = str(reason or "").strip()
    if not (3 <= len(reviewer) <= 150 and 10 <= len(reason) <= 1000):
        raise ValueError("Explicit human reviewer and justification required.")
    manifest = _manifest(root)
    if not isinstance(manifest, dict) or manifest.get("status") != "STAGED_NOT_APPROVED":
        raise ValueError("Candidate is not staged.")
    if manifest["coreSha256"] != core_digest(root):
        raise ValueError("Core BA rules changed; run the evaluation again.")
    check = assess(root)
    if check["status"] != "ELIGIBLE_FOR_HUMAN_APPROVAL":
        raise ValueError("Incomplete/failed independent human evaluation, approval forbidden.")
    eval_dir = root / "data/evaluation"
    fingerprints = {}
    for name in ("selected_cases.json", "baseline_predictions.json", "candidate_predictions.json", "reviews.json"):
        f = eval_dir / name
        if not f.is_file() or f.is_symlink():
            raise ValueError("Missing frozen A/B evidence file.")
        fingerprints[name] = hashlib.sha256(f.read_bytes()).hexdigest()
    current = read_json(directory(root) / "active.json", {})
    if current.get("status") == "APPROVED":
        raise ValueError("Roll back active prompt before approving new experiment.")
    record = {
        "status": "APPROVED", "approvedAt": utc_now(),
        "variantSha256": manifest["variantSha256"],
        "coreSha256": manifest["coreSha256"], "reviewer": reviewer,
        "reason": reason, "cohort": check["cohort"],
        "reviewFingerprints": fingerprints, "realCases": "HUMAN_REVIEWED_LOCAL_ONLY",
    }
    write_json(directory(root) / "active.json", record, 20000)
    return record


def rollback(root=ROOT, reason=""):
    root = Path(root)
    record = read_json(directory(root) / "active.json", {})
    if not isinstance(record, dict) or record.get("status") != "APPROVED":
        raise ValueError("No active approved prompt to roll back.")
    reason = str(reason or "").strip()
    if len(reason) < 8 or len(reason) > 1000:
        raise ValueError("Rollback requires an explicit reason.")
    record["status"] = "ROLLED_BACK"
    record["rolledBackAt"] = utc_now()
    record["rollbackReason"] = reason
    write_json(directory(root) / "active.json", record, 20000)
    return {"status": "ROLLED_BACK", "variantSha256": record["variantSha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("stage", "generate", "assess", "approve", "rollback"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--candidate-file", type=Path)
    parser.add_argument("--variant", choices=("baseline", "candidate"), default="candidate")
    parser.add_argument("--rationale", default="")
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--reason", default="")
    args = parser.parse_args()
    if args.command == "stage":
        result = stage(args.root, args.candidate_file, args.rationale)
    elif args.command == "generate":
        result = generate(args.root, args.variant)
    elif args.command == "assess":
        result = assess(args.root)
    elif args.command == "approve":
        result = approve(args.root, args.reviewer, args.reason)
    else:
        result = rollback(args.root, args.reason)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
