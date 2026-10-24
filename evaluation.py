"""Local, independent BA output evaluation on 20–30 real Jira cases.

No network, Jira writes, model calls or synthetic claims of accuracy.
Corporate descriptions and reviewer labels remain in data/evaluation/ (Git-ignored).
"""
import argparse
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path

from app_config import ROOT, utc_now
from storage import write_json

RUBRIC = (
    "context_accuracy", "evidence_support", "decision_history",
    "scope_and_requirements", "question_usefulness", "qa_correctness",
    "next_action_clarity",
)
MIN_CASES, MAX_CASES = 20, 30
TOPICS = (
    ("rebooking", ("rebook", "exchange", "involuntary")),
    ("refund", ("refund", "cancel")),
    ("baggage", ("baggage", "abag")),
    ("ancillaries", ("extra", "ancillary", "seat", "service")),
    ("multi_city", ("multi-city", "multicity", "journey")),
    ("fare", ("fare", "price", "tax")),
    ("ndc", ("ndc", "offer", "order")),
)


def topic(issue):
    raw = (issue.get("summary", "") + " " + issue.get("description", "")).lower()
    for name, words in TOPICS:
        if any(word in raw for word in words):
            return name
    return "other"


def complexity(issue):
    comments = len(issue.get("comments", []))
    links = len(issue.get("links", []))
    description = len(issue.get("description") or "")
    if comments >= 5 or links >= 3 or description >= 5000:
        return "high"
    if comments == 0 and links == 0 and description < 1000:
        return "low"
    return "medium"


def select_cases(issues, count=30):
    """Deterministic round-robin stratification, no claim of statistical representativeness."""
    if not MIN_CASES <= count <= MAX_CASES:
        raise ValueError("Evaluation count must be between 20 and 30.")
    if len(issues) < count:
        raise ValueError(f"Only {len(issues)} cached Jira tasks; {count} required. "
                         "Run a complete Jira sync or use count 20–30.")
    groups = defaultdict(list)
    for key, issue in issues.items():
        if not isinstance(issue, dict):
            raise ValueError("Invalid issue context.")
        groups[(complexity(issue), topic(issue))].append(key)
    for keys in groups.values():
        keys.sort(key=lambda k: hashlib.sha256(k.encode()).hexdigest())
    chosen = []
    # Consume across complexity and topic strata. This is diverse, not a random sample.
    while len(chosen) < count:
        moved = False
        for group in sorted(groups):
            if groups[group]:
                chosen.append(groups[group].pop(0))
                moved = True
                if len(chosen) == count:
                    break
        if not moved:
            break
    return chosen


def eval_directory(root):
    return Path(root) / "data" / "evaluation"


def prepare(root=ROOT, count=30):
    root = Path(root)
    path = root / "data" / "jira_context.json"
    if not path.exists():
        raise ValueError("Missing data/jira_context.json; run the existing read-only Jira sync.")
    source = json.loads(path.read_text(encoding="utf-8-sig"))
    if source.get("complete") is not True or not isinstance(source.get("issues"), dict):
        raise ValueError("Jira context is not confirmed complete; no evaluation set created.")
    selected = select_cases(source["issues"], count)
    directory = eval_directory(root)
    cases_path = directory / "selected_cases.json"
    reviews_path = directory / "reviews.json"
    if cases_path.exists() or reviews_path.exists():
        raise ValueError("Evaluation set already exists. Preserve your reviews; "
                         "archive or remove it manually before starting a new cohort.")
    cases = []
    for key in selected:
        issue = source["issues"][key]
        cases.append({
            "key": key,
            "summary": issue.get("summary", ""),
            "complexity": complexity(issue),
            "topic": topic(issue),
            "contextFingerprint": issue.get("fingerprint", ""),
            "source": {
                "description": issue.get("description", ""),
                "descriptionAdf": issue.get("descriptionAdf"),
                "jiraStatus": issue.get("jiraStatus", ""),
                "comments": [
                    {k: comment.get(k) for k in ("id", "created", "updated", "body", "bodyAdf", "author")}
                    for comment in issue.get("comments", [])
                ],
                "links": issue.get("links", []),
                "attachments": [
                    {k: attachment.get(k) for k in ("id", "filename", "mimeType", "size", "created")}
                    for attachment in issue.get("attachments", [])
                ],
                "linkedContexts": [
                    {"key": linked, "summary": linked_issue.get("summary", ""),
                     "description": linked_issue.get("description", ""),
                      "descriptionAdf": linked_issue.get("descriptionAdf"),
                     "comments": [
                        {k: comment.get(k) for k in ("id", "created", "updated", "body", "bodyAdf", "author")}
                        for comment in linked_issue.get("comments", [])
                     ], "url": linked_issue.get("url", "")}
                    for linked in [relation.get("linkedKey") for relation in issue.get("links", [])]
                    for linked_issue in [source["issues"].get(linked) or
                                         source.get("linkedIssues", {}).get(linked)]
                    if isinstance(linked_issue, dict)
                ],
                "blockedBy": issue.get("blockedBy", []),
                "parentKey": issue.get("parentKey", ""),
                "url": issue.get("url", ""),
            },
        })
    directory.mkdir(parents=True, exist_ok=True)
    data = {
        "createdAt": utc_now(), "count": count,
        "sourceGeneratedAt": source.get("generatedAt", ""),
        "policy": "LOCAL_ONLY_DO_NOT_COMMIT_OR_UPLOAD",
        "cases": cases,
    }
    reviews = {
        "caseKeys": selected, "rubric": list(RUBRIC),
        "instruction": "Human reviewer must score BOTH versions independently. "
                       "0=wrong/missing, 1=poor, 2=partial, 3=good, 4=verified/excellent. "
                       "Critical false claims must be written verbatim.",
        "reviews": [
            {"key": key, "reviewer": "", "baseline": empty_review(),
             "candidate": empty_review(), "notes": ""}
            for key in selected
        ],
    }
    write_json(cases_path, data)
    write_json(reviews_path, reviews)
    return {"cases": count, "path": str(cases_path), "reviews": str(reviews_path),
            "topicCounts": {name: sum(item["topic"] == name for item in cases)
                            for name in sorted({i["topic"] for i in cases})}}


def attach_predictions(root, variant, analysis_file):
    """Freeze a full analyzed output for the preselected cohort without uploading it."""
    if variant not in ("baseline", "candidate"):
        raise ValueError("variant must be baseline or candidate.")
    directory = eval_directory(root)
    pack = json.loads((directory / "selected_cases.json").read_text(encoding="utf-8"))
    payload = json.loads(Path(analysis_file).read_text(encoding="utf-8-sig"))
    if isinstance(payload.get("analyses"), dict):
        predictions = payload["analyses"]
    elif isinstance(payload.get("tasks"), list):
        predictions = {task["key"]: task.get("analysis") for task in payload["tasks"]}
    else:
        raise ValueError("Expected analyses map or analyzed snapshot tasks.")
    selected = {}
    for case in pack["cases"]:
        key = case["key"]
        analysis = predictions.get(key)
        if not isinstance(analysis, dict) or not analysis.get("signal"):
            raise ValueError(f"{variant}: analysis missing for {key}; no file saved.")
        if analysis.get("contextFingerprint") != case["contextFingerprint"]:
            raise ValueError(f"{variant}: source fingerprint mismatch for {key}; "
                             "evaluate the same frozen Jira context.")
        selected[key] = analysis
    target = directory / (variant + "_predictions.json")
    if target.exists():
        raise ValueError(f"{variant} predictions already frozen; do not replace an evaluated version.")
    write_json(target, {
        "variant": variant, "createdAt": utc_now(), "cohort": len(selected),
        "policy": "LOCAL_ONLY_DO_NOT_COMMIT_OR_UPLOAD",
        "analyses": selected,
    })
    return {"variant": variant, "count": len(selected), "path": str(target)}


def empty_review():
    return {
        "scores": {name: None for name in RUBRIC},
        "criticalFalseClaims": [],
        "minutesSpent": None,
        "reviewed": False,
    }


def validate_review(row):
    if not isinstance(row, dict) or not isinstance(row.get("reviewer"), str):
        raise ValueError("Reviewer name is missing.")
    if not row["reviewer"].strip():
        return False
    for variant in ("baseline", "candidate"):
        entry = row.get(variant)
        if not isinstance(entry, dict) or not isinstance(entry.get("reviewed"), bool):
            raise ValueError("Missing review object for " + variant)
        if not entry["reviewed"]:
            return False
        scores = entry.get("scores")
        if not isinstance(scores, dict) or set(scores) != set(RUBRIC):
            raise ValueError("Invalid score dimensions: " + variant)
        for name in RUBRIC:
            if type(scores[name]) is not int or not 0 <= scores[name] <= 4:
                raise ValueError(f"{variant}.{name} must be an integer from 0 to 4.")
        if not isinstance(entry.get("criticalFalseClaims"), list) or any(
                not isinstance(v, str) or not v.strip() for v in entry["criticalFalseClaims"]):
            raise ValueError("criticalFalseClaims must be a list of human-written descriptions.")
        minutes = entry.get("minutesSpent")
        if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or not 0 < minutes <= 480:
            raise ValueError(f"{variant}.minutesSpent must be >0 and <=480.")
    return True


def score_pack(pack, reviews):
    keys = [c["key"] for c in pack.get("cases", [])]
    if len(keys) != len(set(keys)) or len(keys) < MIN_CASES:
        raise ValueError("Invalid evaluation cohort; at least 20 unique real Jira cases required.")
    listed = reviews.get("reviews")
    if not isinstance(listed, list) or {item["key"] for item in listed} != set(keys) or len(listed) != len(keys):
        raise ValueError("Reviewed cases do not match the frozen selection.")
    completed = []
    for row in listed:
        if validate_review(row):
            completed.append(row)
    summary = {
        "cohort": len(keys), "completed": len(completed),
        "pending": len(keys) - len(completed),
        "status": "INCOMPLETE" if len(completed) != len(keys) else "REVIEWED",
        "policy": "HUMAN_EVALUATION_ONLY_NOT_AUTOMATED_TRUTH",
    }
    if not completed:
        return summary
    metrics = {}
    for variant in ("baseline", "candidate"):
        rated = [row[variant] for row in completed]
        metrics[variant] = {
            "overallMean": round(statistics.mean(
                r["scores"][k] for r in rated for k in RUBRIC), 3),
            "rubric": {
                k: {
                    "mean": round(statistics.mean(row["scores"][k] for row in rated), 3),
                    "goodRate": round(sum(row["scores"][k] >= 3 for row in rated) / len(rated), 3),
                } for k in RUBRIC
            },
            "criticalFalseClaims": sum(len(r["criticalFalseClaims"]) for r in rated),
            "medianMinutes": round(statistics.median(r["minutesSpent"] for r in rated), 2),
        }
    savings = [(row["baseline"]["minutesSpent"] - row["candidate"]["minutesSpent"])
               / row["baseline"]["minutesSpent"] for row in completed]
    summary["metrics"] = metrics
    summary["medianTimeSavedPercent"] = round(statistics.median(savings) * 100, 1)
    # Targets are acceptance criteria, NOT measured claims of deployment quality.
    summary["targets"] = {
        "minGoodRateEachDimension": 0.90,
        "maxCriticalFalseClaims": 0,
        "minMedianTimeSavedPercent": 40.0,
    }
    summary["candidateMeetsTargets"] = (
        len(completed) == len(keys)
        and all(dim["goodRate"] >= 0.9 for dim in metrics["candidate"]["rubric"].values())
        and metrics["candidate"]["criticalFalseClaims"] == 0
        and summary["medianTimeSavedPercent"] >= 40
    )
    return summary


def render_score(result):
    lines = [
        "# CCON BA case evaluation",
        "",
        "Dataset: real cached Jira issues only, reviewed by a human. "
        "A passing code test is not evidence of correct BA output.",
        "",
        f"Evaluated: {result['completed']}/{result['cohort']}; status: {result['status']}",
    ]
    if not result.get("metrics"):
        return "\n".join(lines) + "\n"
    lines += ["", "| Criterion | Before | After |", "|---|---:|---:|"]
    for criterion in RUBRIC:
        base = result["metrics"]["baseline"]["rubric"][criterion]
        after = result["metrics"]["candidate"]["rubric"][criterion]
        lines.append(f"| {criterion} (mean / >=3 share) | {base['mean']} / {base['goodRate']:.0%} | "
                     f"{after['mean']} / {after['goodRate']:.0%} |")
    lines += [
        "",
        f"Critical false claims: {result['metrics']['baseline']['criticalFalseClaims']} before, "
        f"{result['metrics']['candidate']['criticalFalseClaims']} after.",
        f"Median time saved: {result['medianTimeSavedPercent']}%.",
        "Targets met: " + ("YES" if result["candidateMeetsTargets"] else "NO / incomplete"),
    ]
    return "\n".join(lines) + "\n"


def evaluate(root=ROOT):
    directory = eval_directory(root)
    cases = json.loads((directory / "selected_cases.json").read_text(encoding="utf-8"))
    reviews = json.loads((directory / "reviews.json").read_text(encoding="utf-8"))
    report = score_pack(cases, reviews)
    frozen = [label for label in ("baseline", "candidate")
              if not (directory / (label + "_predictions.json")).exists()]
    if frozen:
        report["status"] = "INCOMPLETE"
        report["missingPredictionSets"] = frozen
        report["candidateMeetsTargets"] = False
    write_json(directory / "results.json", report)
    (directory / "results.md").write_text(render_score(report), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description="Prepare and grade LOCAL real-Jira BA evaluation.")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("prepare", help="select 20–30 real cached Jira issues for manual A/B review")
    create.add_argument("--count", type=int, default=30)
    grade = sub.add_parser("score", help="score completed human review forms")
    attach = sub.add_parser("attach", help="freeze baseline/candidate predictions for the selected cohort")
    attach.add_argument("--variant", choices=("baseline", "candidate"), required=True)
    attach.add_argument("--analysis-file", required=True, type=Path)
    for cmd in (create, grade, attach):
        cmd.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args.root, args.count)
        elif args.command == "attach":
            result = attach_predictions(args.root, args.variant, args.analysis_file)
        else:
            result = evaluate(args.root)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(1, "Evaluation failed: " + str(exc) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
