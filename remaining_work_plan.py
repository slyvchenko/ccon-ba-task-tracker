"""Deterministic, public-safe work plan for *unfinished* BA Desk backlog items.

Reads only the canonical source-controlled requirement ledger; no Jira, tokens,
private SQL, ZIP or approval records are ever accessed.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / "docs/BACKLOG_ACCEPTANCE_LEDGER.json"
TARGET = ROOT / "docs/REMAINING_WORK_PLAN.md"
LANES = (
    ("PRIVATE_UAT", "Приватне BA/Windows приймання"),
    ("P0_SOURCE", "Критичні P0 докази та достовірність"),
    ("P1_WORKFLOW", "P1 робочий процес, безпека і надійність"),
    ("P2_SCOPE", "P2 експерименти та можливе спрощення"),
    ("CLOUD_DEFERRED", "P3 хмарний продукт лише за окремим рішенням"),
)


def lane(row):
    if row["category"] == "DEFERRED":
        return "CLOUD_DEFERRED"
    if row["category"] == "GATE" or row["id"] == "QA-13":
        return "PRIVATE_UAT"
    return {"P0": "P0_SOURCE", "P1": "P1_WORKFLOW", "P2": "P2_SCOPE",
            "P3": "CLOUD_DEFERRED"}[row["priority"]]


def action(row):
    state = row["category"]
    if state == "DEFERRED":
        return "Не реалізовувати у локальному scope без product approval."
    if state == "GATE" or row["id"] == "QA-13":
        return "Виконати незалежне приватне приймання за DoD."
    if row["priority"] == "P2":
        return "Спершу usage/overlap review; потім build або явно defer."
    if state == "PLANNED":
        return "Розробити код + синтетичні тести; потім реальна перевірка."
    return "Закрити відсутню частину DoD кодом/тестом або приватним UAT."


def escape(value):
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def make_plan(ledger):
    rows = ledger["items"]
    if len(rows) != 129 or len({r["id"] for r in rows}) != 129:
        raise ValueError("Expected exactly 129 unique canonical backlog requirements")
    if any(r["human_acceptance"] != "NOT_RECORDED" for r in rows):
        raise ValueError("Human approval is outside the public plan")
    open_rows = [r for r in rows if r["category"] != "IMPLEMENTED"]
    out = [
        "# CCON BA Desk: реєстр усієї незавершеної роботи після v2.48.1",
        "",
        "**Джерело:** `docs/BACKLOG_ACCEPTANCE_LEDGER.json` з `docs/PRODUCT_BACKLOG.md`. "
        "**План, не факт виконання.** Реальні Jira/CCON/Kibana й людське BA-приймання "
        "не можна закрити синтетичним CI.",
        "",
        f"**В інвентарі:** {len(rows)} вимог; {len(rows)-len(open_rows)} з code-reported "
        f"IMPLEMENTED (також без human acceptance); **{len(open_rows)} залишилися "
        "відкритими для реалізації, перевірки, scope-рішення або UAT**.",
        "",
        "## Порядок реалізації",
        "",
        "1. Спершу P0 real source / 26-case QA / privacy gates: жодного false-ready чи "
        "непідтвердженого XML/PNR/mapping.",
        "2. Далі P1 функції, які скорочують час BA без зміни hard sprint/WRITE lanes "
        "і без автоматичного Jira/email write.",
        "3. Потім P2: лише після перевірки дублювання (16 VIS), користі та UX, "
        "щоб не множити вкладки, dashboards і шаблони.",
        "4. P3 cloud/SSO/PostgreSQL не входить до локального релізу без окремого рішення.",
        "",
        "## Інвентар відкритих робіт",
        "",
    ]
    for code, heading in LANES:
        group = [r for r in open_rows if lane(r) == code]
        out += [f"### {heading} ({len(group)})", "",
                "| ID | P | Стан | Дія / рішення | Критерій виконання |",
                "|---|---|---|---|---|"]
        for r in group:
            step = action(r)
            if r.get("possible_overlaps"):
                step += " Перевірити перетин: " + ", ".join(r["possible_overlaps"]) + "."
            out.append("| " + " | ".join((
                escape(r["id"]), escape(r["priority"]), escape(r["category"]),
                escape(step), escape(r["acceptance_criteria"]))) + " |")
        out.append("")
    out += [
        "## Правила приймання і закриття",
        "",
        "- Усі `human_acceptance` залишаються `NOT_RECORDED`; GitHub PR та CI "
        "не є бізнес-узгодженням.",
        "- Для кожного P0/P1 зазначити реалізацію, тести, source proof і "
        "залишкові UAT-gates; не ставити DONE за існування файла.",
        "- Для P2/P3 - явне product рішення KEEP / CONSOLIDATE / DEFER / DROP "
        "з обґрунтуванням, без автоматичного видалення вимог.",
        "- Реальні дані, скриншоти з Jira, supplier ZIP, token, PNR та "
        "приватний QA-звіт не вивантажувати до публічного репозиторію.",
        "- Пов'язаний live-acceptance blocker: GitHub Issue #50.",
        "",
    ]
    return "\n".join(out)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true")
    args = p.parse_args(argv)
    try:
        value = make_plan(json.loads(LEDGER.read_text(encoding="utf-8")))
        if args.check:
            if TARGET.read_text(encoding="utf-8") != value:
                raise ValueError("Remaining work plan is stale")
            print("Remaining backlog plan: all open items accounted for.")
        else:
            TARGET.write_text(value, encoding="utf-8")
            print("Updated docs/REMAINING_WORK_PLAN.md")
    except (OSError, ValueError, KeyError) as e:
        print("Remaining work plan failed: " + str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
