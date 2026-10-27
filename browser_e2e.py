"""Opt-in real Chromium DOM E2E, synthetic task data ONLY.

Run: python -m pip install playwright==1.56.0
     python -m playwright install chromium
     python browser_e2e.py

Never exercises real Jira, Outlook, mailto sending or external attachments.
Not included in Python-only startup dependencies.
"""
import hashlib
import json
import os
import statistics
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from desk_store import Desk
from server import handler

ARTIFACTS = Path(os.getenv("CCON_BROWSER_ARTIFACTS", "browser-artifacts"))
SYNTH = "Synthetic E2E only, no supplier or real Jira source"


def recorded_failure(result, testcase):
    """Check the recorded unittest result; _outcome.success resets in tearDown."""
    if result is None:
        return False
    return any(test is testcase for test, _ in
               list(result.failures) + list(result.errors))


def fixture_document(moment="2026-10-25T09:00:00Z"):
    def analysis(signal, score):
        return {"signal": signal, "reasonUk": "Синтетичний сценарій для QA",
                "nextActionUk": "Перевірити і вручну ухвалити рішення",
                "needsEmail": signal == "WRITE", "queueScore": score,
                "waitingRequired": False, "missingInfo": [],
                "emailDraft": {
                    "to": "synthetic@example.invalid", "subject": "Synthetic case",
                    "body": "This is not a real supplier message."}}
    return {"generatedAt": moment, "tasks": [
        {"key": "CCON-1", "summary": "Synthetic deep investigation",
         "activeSprintStatus": "VERIFIED", "activeSprint": True,
         "analysis": analysis("REVIEW", 88)},
        {"key": "CCON-2", "summary": "Synthetic ready supplier letter",
         "activeSprintStatus": "VERIFIED", "activeSprint": True,
         "analysis": analysis("WRITE", 90)},
        {"key": "CCON-3", "summary": "Synthetic backlog task",
         "activeSprintStatus": "VERIFIED", "activeSprint": False,
         "analysis": analysis("READY", 30)},
    ]}


class BrowserRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.engine = sync_playwright().start()
        cls.browser = cls.engine.chromium.launch(headless=True, args=["--no-sandbox"])
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        cls.timings = []

    @classmethod
    def tearDownClass(cls):
        ARTIFACTS.joinpath("synthetic-browser-results.json").write_text(json.dumps({
            "syntheticOnly": True, "engine": "Chromium on CI runner",
            "tests": len(cls.timings),
            "results": cls.timings,
            "notMeasured": ["Windows Chrome/Edge", "8-hour memory endurance",
                            "NVDA", "400% native browser zoom", "real supplier correctness"]
        }, indent=2), encoding="utf-8")
        cls.browser.close()
        cls.engine.stop()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ccon-browser-e2e-")
        self.root = Path(self.temp.name)
        self.desk = Desk(self.root)
        self.snapshot = self.desk.inbox / "CCON_BA_Snapshot.json"
        self.snapshot.write_text(json.dumps(fixture_document()), encoding="utf-8")
        self.desk.import_snapshot()
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), handler(self.desk))
        self.worker = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.worker.start()
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 820},
                                                accept_downloads=False)
        self.page = self.context.new_page()
        self.pageerrors = []
        self.page.on("pageerror", lambda error: self.pageerrors.append(str(error)))
        self.page.goto(self.url, wait_until="domcontentloaded")
        self.page.locator("#list button[data-key]").first.wait_for(timeout=15000)

    def tearDown(self):
        if self.pageerrors:
            ARTIFACTS.joinpath(self.id().split(".")[-1] + "-errors.json").write_text(
                json.dumps(self.pageerrors, ensure_ascii=False), encoding="utf-8")
        try:
            if self._outcome and recorded_failure(self._outcome.result, self):
                self.page.screenshot(path=str(ARTIFACTS /
                    (self.id().split(".")[-1] + "-failed.png")),full_page=True)
        except Exception:
            pass
        self.context.close()
        self.http.shutdown()
        self.http.server_close()
        self.worker.join(timeout=5)
        self.temp.cleanup()
        self.assertFalse(self.pageerrors, "Unhandled browser JavaScript error(s)")

    def choose(self, key, page=None):
        page = page or self.page
        page.locator(f'#list button[data-key="{key}"]').click()
        page.locator("#note").wait_for()
        self.assertIn(key, page.locator("#detail .task-key").inner_text())

    def test_keyboard_navigation_save_and_priority(self):
        self.assertEqual(self.page.locator("#list button[data-key]").count(), 3)
        self.assertEqual(self.page.locator("#list button[data-key]").first.get_attribute("data-key"),
                         "CCON-2")  # WRITE within confirmed active sprint
        self.choose("CCON-1")
        self.page.locator("#note").fill("A safe synthetic note")
        self.page.locator("#save").click()
        self.page.wait_for_function(
            "() => document.querySelector('#savedIndicator')?.hidden === false")
        note = next(t for t in self.desk.view()["tasks"] if t["key"] == "CCON-1")
        self.assertEqual(note["note"], "A safe synthetic note")
        self.page.locator('#list button[data-key="CCON-1"]').focus()
        self.page.keyboard.press("Alt+ArrowDown")
        self.page.wait_for_function(
            "() => !!document.querySelector('#list button[data-key=CCON-3][aria-pressed=true]')")
        self.assertFalse(self.page.locator("#bulkDialog").evaluate("(el)=>el.open"))

    def test_two_tabs_reload_unsaved_and_CAS_conflict(self):
        second = self.context.new_page()
        second.goto(self.url,wait_until="domcontentloaded")
        second.locator('#list button[data-key="CCON-1"]').wait_for()
        self.choose("CCON-1")
        self.choose("CCON-1",second)
        self.page.locator("#note").fill("Synthetic TAB A")
        second.locator("#note").fill("Synthetic TAB B")
        own_ids=self.page.evaluate("""() => Object.keys(localStorage).filter(
            key=>key.startsWith('ccon-ba-desk.unsaved-tab.v3.'))""")
        self.assertGreaterEqual(len(own_ids),2)
        self.page.reload()
        second.reload()
        self.page.locator("#note").wait_for()
        second.locator("#note").wait_for()
        self.assertEqual(self.page.locator("#note").input_value(),"Synthetic TAB A")
        self.assertEqual(second.locator("#note").input_value(),"Synthetic TAB B")
        self.page.locator("#save").click()
        self.page.wait_for_function(
            "() => document.querySelector('#savedIndicator')?.hidden === false")
        second.locator("#save").click()
        second.locator("#manualConflict").wait_for(state="visible",timeout=15000)
        self.assertEqual(second.locator("#note").input_value(),"Synthetic TAB B")
        self.assertEqual(next(t["note"] for t in self.desk.view()["tasks"]
                              if t["key"]=="CCON-1"),"Synthetic TAB A")
        second.close()

    def test_clean_focused_form_cannot_adopt_new_revision_from_another_tab(self):
        # Regression of historical PR #30 review: a stale DOM held under
        # focus must never silently overwrite another tab after background poll.
        second = self.context.new_page()
        second.goto(self.url, wait_until="domcontentloaded")
        second.locator('#list button[data-key="CCON-1"]').wait_for()
        self.choose("CCON-1")
        self.choose("CCON-1", second)
        self.assertEqual(self.page.locator("#note").input_value(), "")
        self.page.locator("#manual").focus()  # clean focused form, no edits

        second.locator("#note").fill("Other tab authoritative note")
        second.locator("#save").click()
        second.wait_for_function(
            "() => document.querySelector('#savedIndicator')?.hidden === false")
        self.assertEqual(next(t["note"] for t in self.desk.view()["tasks"]
                              if t["key"] == "CCON-1"),
                         "Other tab authoritative note")

        # Wait for the real five-second background poll, not a page reload.
        self.page.locator("#manualConflict").wait_for(state="visible", timeout=18000)
        self.assertEqual(self.page.locator("#note").input_value(), "",
                         "stale visible fields stay attached to their old revision")
        self.assertTrue(self.page.locator("#done").is_disabled())
        self.assertEqual(next(t["note"] for t in self.desk.view()["tasks"]
                              if t["key"] == "CCON-1"),
                         "Other tab authoritative note")
        second.close()

    def test_manual_done_can_be_undone_once_without_external_jira_write(self):
        self.choose("CCON-1")
        self.assertTrue(self.page.locator("#undoLastDone").is_hidden())
        self.page.on("dialog",lambda dialog:dialog.accept())
        self.page.locator("#done").click()
        self.page.locator("#undoLastDone").wait_for(state="visible",timeout=15000)
        task = next(t for t in self.desk.view()["tasks"] if t["key"]=="CCON-1")
        self.assertEqual(task["manualStatus"],"DONE")
        self.page.locator("#undoLastDone").click()
        self.page.wait_for_function("() => document.querySelector('#undoLastDone').hidden")
        task = next(t for t in self.desk.view()["tasks"] if t["key"]=="CCON-1")
        self.assertEqual(task["manualStatus"],"AUTO")
        self.assertEqual(self.page.locator("#detail .task-key").inner_text(),"CCON-1")

    def test_supplier_recipient_hint_requires_explicit_click_and_empty_to_persists(self):
        document=fixture_document()
        document["tasks"][1]["summary"]="AF/KL. Synthetic supplier request"
        document["tasks"][1]["analysis"]["emailDraft"]["to"]=""
        self.snapshot.write_text(json.dumps(document),encoding="utf-8")
        self.desk.import_snapshot()
        self.page.reload()
        self.page.locator('#list button[data-key="CCON-2"]').wait_for()
        self.choose("CCON-2")
        self.assertEqual(self.page.locator("#draftTo").input_value(),"")
        self.assertTrue(self.page.locator("#useRecipientHint").is_visible())
        self.assertIn("не підтверджена",self.page.locator("#recipientHintWarning").inner_text())
        self.page.locator("#useRecipientHint").click()
        self.assertIn("@airfrance.fr",self.page.locator("#draftTo").input_value())
        self.page.locator("#save").click()
        self.page.wait_for_function(
            "() => document.querySelector('#savedIndicator')?.hidden === false")
        self.assertIn("@airfrance.fr",
            next(t for t in self.desk.view()["tasks"] if t["key"]=="CCON-2")["savedEmailDraft"]["to"])
        self.page.locator("#draftTo").fill("")
        self.page.locator("#save").click()
        self.page.wait_for_function(
            "() => document.querySelector('#savedIndicator')?.hidden === false")
        self.page.reload()
        self.page.locator('#list button[data-key="CCON-2"]').wait_for()
        self.choose("CCON-2")
        self.assertEqual(self.page.locator("#draftTo").input_value(),"")

    def test_personal_focus_pin_is_session_only_and_cannot_bypass_sprint_write(self):
        document=fixture_document()
        document["tasks"][0]["analysis"]["priorityFactors"]={
            "businessImpact":25,"urgency":20,"dependencies":15,
            "baDecision":20,"actionability":8}
        extra=json.loads(json.dumps(document["tasks"][0]))
        extra["key"]="CCON-4"
        extra["summary"]="Synthetic higher score same action group"
        extra["analysis"].pop("priorityFactors")
        extra["analysis"]["queueScore"]=95
        document["tasks"].append(extra)
        self.snapshot.write_text(json.dumps(document),encoding="utf-8")
        self.desk.import_snapshot()
        self.page.reload()
        self.page.locator('#list button[data-key="CCON-4"]').wait_for()
        def order():
            return self.page.locator('#list button[data-key]').evaluate_all(
                "(nodes)=>nodes.map(node=>node.dataset.key)")
        self.assertEqual(order(),["CCON-2","CCON-4","CCON-1","CCON-3"])
        self.choose("CCON-1")
        self.page.locator("summary").filter(
            has_text="Пріоритет і орієнтовний обсяг").click()
        self.assertIn("Вплив: 25/25",self.page.locator(".effort-summary").inner_text())
        self.assertIn("Терміновість: 20/25",self.page.locator(".effort-summary").inner_text())
        self.page.locator("#pinDeepWork").click()
        self.assertEqual(order(),["CCON-2","CCON-1","CCON-4","CCON-3"])
        self.assertTrue(self.page.locator("#pinDeepWork").evaluate(
            "(node)=>document.activeElement===node"))
        self.assertEqual(self.page.evaluate(
            "()=>sessionStorage.getItem('ccon-ba-desk.personal-focus-pin.v1')"),
            "CCON-1")
        self.page.reload()
        self.page.locator('#list button[data-key="CCON-4"]').wait_for()
        self.assertEqual(order(),["CCON-2","CCON-1","CCON-4","CCON-3"])
        self.choose("CCON-1")
        # View-state restore can keep this existing <details> open after reload.
        if not self.page.locator("#pinDeepWork").is_visible():
            self.page.locator("summary").filter(
                has_text="Пріоритет і орієнтовний обсяг").click()
        self.page.locator("#pinDeepWork").click()
        self.assertEqual(order(),["CCON-2","CCON-4","CCON-1","CCON-3"])
        self.assertIsNone(self.page.evaluate(
            "()=>sessionStorage.getItem('ccon-ba-desk.personal-focus-pin.v1')"))
        self.assertEqual(next(t for t in self.desk.view()["tasks"] if t["key"]=="CCON-1")
                         ["analysis"]["queueScore"],88)

    def test_save_restores_focus_to_enabled_note_not_hidden_save(self):
        self.choose("CCON-1")
        self.page.locator("#note").fill("Synthetic save focus check")
        self.page.locator("#save").click()
        self.page.wait_for_function(
            "()=>document.querySelector('#savedIndicator')?.hidden===false")
        self.page.wait_for_function(
            "()=>document.activeElement?.id==='note'")
        self.assertTrue(self.page.locator("#note").is_enabled())
        self.assertTrue(self.page.locator("#save").is_hidden())
        self.assertEqual(self.page.locator("#note").input_value(),
                         "Synthetic save focus check")

    def test_bulk_failure_focuses_retry_and_escape_returns_to_launcher(self):
        self.page.route("**/api/email/open-batch",lambda route:route.fulfill(
            status=503,content_type="application/json",
            body='{"error":"Synthetic retry only"}'))
        self.page.locator("#bulkEmail").click()
        self.page.locator("#bulkDialog").wait_for(state="visible")
        self.assertTrue(self.page.locator("#bulkOpen").is_enabled())
        self.page.locator("#bulkOpen").click()
        self.page.wait_for_function(
            "()=>document.activeElement?.id==='bulkOpen' && "
            "!document.querySelector('#bulkOpen').disabled")
        self.page.keyboard.press("Escape")
        self.page.locator("#bulkDialog").wait_for(state="hidden")
        self.assertTrue(self.page.locator("#bulkEmail").evaluate(
            "(node)=>document.activeElement===node"))

    def test_bulk_modal_escape_restores_focus_and_never_opens_email(self):
        requests=[]
        self.page.on("request",lambda req: requests.append(req.url)
                     if req.method=="POST" else None)
        opener=self.page.locator("#bulkEmail")
        self.assertTrue(opener.is_enabled())
        opener.click()
        self.page.locator("#bulkDialog").wait_for(state="visible")
        self.assertTrue(self.page.locator("#bulkClose").evaluate(
            "(node)=>document.activeElement===node"))
        self.page.keyboard.press("Escape")
        self.page.locator("#bulkDialog").wait_for(state="hidden")
        self.assertTrue(opener.evaluate("(node)=>document.activeElement===node"))
        self.assertFalse(any("/api/email/open-batch" in url for url in requests))

    def test_read_disconnect_reconnect_keeps_dirty_note_without_POST_replay(self):
        self.choose("CCON-1")
        self.page.locator("#note").fill("Offline and not submitted")
        submitted=[]
        self.page.on("request",lambda req: submitted.append(req.url)
                     if req.method=="POST" else None)
        self.page.route("**/api/tasks/revision",lambda route:route.abort())
        self.page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        self.page.wait_for_function(
            "() => document.querySelector('#message')?.textContent.includes('З’єднання втрачено')",
            timeout=15000)
        self.assertEqual(self.page.locator("#note").input_value(),"Offline and not submitted")
        self.page.unroute("**/api/tasks/revision")
        self.page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        self.page.wait_for_function(
            "() => document.querySelector('#message')?.textContent.includes('З’єднання відновлено')",
            timeout=15000)
        self.assertEqual(self.page.locator("#note").input_value(),"Offline and not submitted")
        self.assertEqual(submitted,[])
        self.page.locator("#save").click()
        self.page.wait_for_function(
            "() => document.querySelector('#savedIndicator')?.hidden === false")
        self.assertEqual(next(t["note"] for t in self.desk.view()["tasks"] if
                              t["key"]=="CCON-1"),"Offline and not submitted")

    def test_snapshot_refresh_preserves_dirty_editor_and_focus(self):
        self.choose("CCON-1")
        self.page.locator("#note").fill("Pending snapshot change")
        refreshed=fixture_document(moment="2026-10-25T12:00:00Z")
        changed=next(t for t in refreshed["tasks"] if t["key"]=="CCON-3")
        changed["summary"]="Observable synthetic background refresh"
        self.snapshot.write_text(json.dumps(refreshed),encoding="utf-8")
        self.desk.import_snapshot()
        self.page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        # This must fail if the dashboard never consumes the new SQLite revision.
        self.page.wait_for_function("""() => {
          const row=document.querySelector('#list button[data-key="CCON-3"] .row-title');
          return row && row.textContent.includes('Observable synthetic background refresh');
        }""",timeout=18000)
        self.assertEqual(self.page.locator("#note").input_value(),"Pending snapshot change")
        self.assertTrue(self.page.locator("#save").is_visible())

    def test_progressive_filters_and_data_grouping_keep_controls_accessible(self):
        advanced=self.page.locator("#advancedFilters")
        self.assertFalse(advanced.evaluate("(el)=>el.open"))
        advanced.locator("summary").click()
        self.page.locator("#signalFilter").select_option("WRITE")
        self.page.locator("#advancedFilterCount").wait_for(state="visible")
        self.assertIn("1 активний",self.page.locator("#advancedFilterCount").inner_text())
        self.assertEqual(self.page.locator("#list button[data-key]").count(),1)
        self.page.locator("#signalFilter").select_option("all")
        self.page.locator("#sprintFilter").select_option("outside")
        self.assertEqual(self.page.locator("#list button[data-key]").count(),1)
        self.page.locator("#sprintFilter").select_option("all")
        self.assertEqual(self.page.locator("#list button[data-key]").count(),3)
        self.page.locator("#dataMenu > summary").click()
        self.assertEqual(self.page.locator(".data-menu-group").count(),3)
        self.assertEqual(self.page.locator("#recoverOther").count(),1)
        self.assertEqual(self.page.locator("#import").count(),1)
        self.page.locator("#dataMenu > summary").click()
        self.choose("CCON-1")
        self.assertEqual(self.page.locator('details[aria-label="Джерела оцінки"]').count(),1)
        self.assertEqual(self.page.locator('details[aria-label="Історія та минулі версії"]').count(),1)
        self.assertEqual(self.page.locator("#taskHistory").count(),1)

    def test_visual_layout_synthetic_screenshots_and_no_horizontal_overflow(self):
        self.choose("CCON-1")
        for width,height in ((320,850),(768,900),(1440,900)):
            self.page.set_viewport_size({"width":width,"height":height})
            self.page.locator("#nextText").wait_for()
            geometry=self.page.evaluate("""() => ({
              documentWidth:document.documentElement.scrollWidth,
              viewportWidth:document.documentElement.clientWidth,
              mainWidth:document.querySelector('#detail').getBoundingClientRect().width,
              queueWidth:document.querySelector('#list').getBoundingClientRect().width
            })""")
            self.assertGreater(geometry["mainWidth"],0)
            self.assertGreater(geometry["queueWidth"],0)
            self.assertLessEqual(geometry["documentWidth"],
                                 geometry["viewportWidth"]+2,
                                 str(geometry))
            self.page.screenshot(path=str(ARTIFACTS /
                f"synthetic-layout-{width}.png"),full_page=True)
        self.assertEqual(self.page.locator("#copyNext").count(),1)

    def test_large_queue_100_500_1000_browser_search_and_reload(self):
        # Browser-backed synthetic cohort, not a Windows benchmark or SLA.
        for index, amount in enumerate((100,500,1000)):
            data={"generatedAt":f"2026-10-25T{15+index:02d}:00:00Z",
                  "tasks":[{"key":f"CCON-{i+1000}",
                            "summary":f"Synthetic API issue {i}",
                            "activeSprint":i%2==0,
                            "activeSprintStatus":"VERIFIED",
                            "analysis":{"signal":"READY",
                                        "reasonUk":"Synthetic explanation",
                                        "nextActionUk":"Review one synthetic scenario",
                                        "queueScore":i%101}}
                           for i in range(amount)]}
            self.snapshot.write_text(json.dumps(data),encoding="utf-8")
            self.desk.import_snapshot()
            start=time.perf_counter()
            self.page.reload(wait_until="domcontentloaded")
            self.page.wait_for_function(
                f"() => document.querySelectorAll('#list button[data-key]').length === {amount}",
                timeout=20000)
            cold_ms=(time.perf_counter()-start)*1000
            timings=[]
            for k in range(5):
                started=time.perf_counter()
                self.page.locator("#search").fill(f"NO_MATCH_FAKE_{index}_{k}")
                self.page.wait_for_function(
                    "() => document.querySelectorAll('#list button[data-key]').length === 0",
                    timeout=15000)
                timings.append((time.perf_counter()-started)*1000)
                self.page.locator("#search").fill("")
                self.page.wait_for_function(
                    f"() => document.querySelectorAll('#list button[data-key]').length === {amount}",
                    timeout=15000)
            self.timings.append({
                "scenario":"Browser DOM large synthetic queue and debounced search",
                "cohortSize":amount,"coldReloadMs":round(cold_ms,2),
                "searchFilterP50Ms":round(statistics.median(timings),2),
                "searchFilterP95Ms":round(sorted(timings)[-1],2),
                "syntheticOnly":True,"notAnSLO":True})
            self.assertTrue(self.page.locator("#detail").is_visible())
            self.assertTrue(self.page.locator("#search").is_visible())

    def test_a11y_semantic_queue_headings_and_forced_color_keyboard_handoff(self):
        self.choose("CCON-2")
        self.page.set_viewport_size({"width":320,"height":850})
        self.page.emulate_media(forced_colors="active", reduced_motion="reduce")
        self.assertTrue(self.page.evaluate(
            "() => matchMedia('(forced-colors: active)').matches"))
        self.assertTrue(self.page.evaluate(
            "() => matchMedia('(prefers-reduced-motion: reduce)').matches"))
        headings=self.page.locator("#list [role=heading][aria-level='3']")
        self.assertGreaterEqual(headings.count(),2)
        self.assertIn("СПРИНТ",headings.first.inner_text().upper())
        for selector in ("#draftTo","#draftSubject","#draftBody","#copyEmail","#email",
                         "#save","#done"):
            self.assertEqual(self.page.locator(selector).count(),1,selector)
        self.assertTrue(self.page.locator("#copyEmail").is_visible())
        self.assertTrue(self.page.locator("#email").is_visible())
        # :focus-visible is defined for keyboard navigation, not necessarily
        # programmatic .focus() in Chromium forced-colors emulation.
        self.page.locator("#copyEmail").focus()
        self.page.keyboard.press("Tab")
        focus=self.page.locator("#email").evaluate(
            "(el)=>({focused:document.activeElement===el,outline:getComputedStyle(el).outlineStyle})")
        self.assertTrue(focus["focused"])
        self.assertNotEqual(focus["outline"],"none")
        geometry=self.page.evaluate("""() => ({
            doc:document.documentElement.scrollWidth,
            viewport:document.documentElement.clientWidth
        })""")
        self.assertLessEqual(geometry["doc"],geometry["viewport"]+2)
        self.assertFalse(self.page.locator("#bulkDialog").evaluate("(el)=>el.open"))

    def test_other_task_import_does_not_refetch_selected_heavy_detail(self):
        # PERF-08: a changed global snapshot must not destroy a stable detail.
        self.choose("CCON-1")
        self.page.wait_for_function(
            "() => (document.querySelector('#taskHistory')?.textContent || '').includes('Історія:')",
            timeout=15000)
        self.page.evaluate("""() => {
            window.__stableNoteNode=document.querySelector('#note');
            document.querySelector('#detail .task-date').textContent='SYNTHETIC OLD IMPORT DATE';
        }""")
        resource_paths=("/api/evidence/", "/api/questions/", "/api/decisions/",
                        "/api/actions/", "/api/history/", "/api/approved/")
        requests=[]
        self.page.on("request", lambda request: requests.append(request.url)
                     if any(resource in request.url for resource in resource_paths) else None)
        next_doc=fixture_document("2026-10-26T09:01:00Z")
        next_doc["tasks"][1]["summary"]="UPDATED SYNTHETIC OTHER TASK"
        self.snapshot.write_text(json.dumps(next_doc),encoding="utf-8")
        self.desk.import_snapshot()
        self.page.evaluate("window.dispatchEvent(new Event('online'))")
        self.page.wait_for_function(
            "() => [...document.querySelectorAll('#list .row-title')].some(el=>el.textContent.includes('UPDATED SYNTHETIC OTHER TASK'))",
            timeout=15000)
        self.assertTrue(self.page.evaluate(
            "() => window.__stableNoteNode===document.querySelector('#note')"))
        self.assertNotEqual(self.page.locator('#detail .task-date').inner_text(),
                            'SYNTHETIC OLD IMPORT DATE')
        self.assertEqual(requests,[], "Unrelated import must not refetch selected evidence/history")
        # Actual selected task content change must still rerender and reload evidence.
        next_doc["generatedAt"]="2026-10-26T09:02:00Z"
        next_doc["tasks"][0]["summary"]="UPDATED SYNTHETIC SELECTED TASK"
        self.snapshot.write_text(json.dumps(next_doc),encoding="utf-8")
        self.desk.import_snapshot()
        self.page.evaluate("window.dispatchEvent(new Event('online'))")
        self.page.wait_for_function(
            "() => document.querySelector('#detail .task-top')?.textContent.includes('CCON-1') && document.querySelector('#detail').textContent.includes('UPDATED SYNTHETIC SELECTED TASK')",
            timeout=15000)
        self.assertFalse(self.page.evaluate(
            "() => window.__stableNoteNode===document.querySelector('#note')"))
        self.page.wait_for_function(
            "() => (document.querySelector('#taskHistory')?.textContent || '').includes('Історія:')",
            timeout=15000)
        self.assertTrue(any("/api/evidence/CCON-1" in url for url in requests))

    def test_keyed_queue_keeps_unmodified_dom_and_focused_row(self):
        # PERF-05: one edited row in a 500-item synthetic snapshot must not
        # destroy the 499 unchanged DOM buttons or their native focus.
        doc={"generatedAt":"2026-10-26T10:00:00Z","tasks":[{
            "key":f"CCON-{1000+i}","summary":f"Synthetic case {i}",
            "activeSprint":True,"activeSprintStatus":"VERIFIED",
            "analysis":{"signal":"READY","queueScore":50,"reasonUk":"Synthetic"}
        } for i in range(500)]}
        self.snapshot.write_text(json.dumps(doc),encoding="utf-8")
        self.desk.import_snapshot()
        self.page.reload(wait_until="domcontentloaded")
        self.page.wait_for_function(
            "() => document.querySelectorAll('#list button[data-key]').length===500",
            timeout=20000)
        target=self.page.locator('#list button[data-key="CCON-1100"]')
        target.focus()
        self.page.evaluate("""() => {
            window.__originalRow=document.querySelector('#list button[data-key="CCON-1100"]');
            window.__changingRow=document.querySelector('#list button[data-key="CCON-1300"]');
        }""")
        doc["generatedAt"]="2026-10-26T10:01:00Z"
        doc["tasks"][300]["summary"]="Updated synthetic row 300"
        self.snapshot.write_text(json.dumps(doc),encoding="utf-8")
        self.desk.import_snapshot()
        self.page.evaluate("window.dispatchEvent(new Event('online'))")
        self.page.wait_for_function(
            "() => document.querySelector('#list button[data-key=CCON-1300]')?.textContent.includes('Updated synthetic row 300')",
            timeout=15000)
        state=self.page.evaluate("""() => ({
            rowUnchanged:window.__originalRow===document.querySelector('#list button[data-key="CCON-1100"]'),
            changedReplaced:window.__changingRow!==document.querySelector('#list button[data-key="CCON-1300"]'),
            focused:document.activeElement===window.__originalRow,
            count:document.querySelectorAll('#list button[data-key]').length
        })""")
        self.assertEqual(state,{"rowUnchanged":True,"changedReplaced":True,
                                "focused":True,"count":500})

    def test_sticky_next_action_only_after_scrolling_existing_detail(self):
        self.choose("CCON-2")
        self.assertTrue(self.page.locator("#stickyAction").is_hidden())
        self.page.locator("#detail").evaluate("(el)=>el.scrollTop=900")
        self.page.wait_for_function(
            "() => document.querySelector('#stickyAction')?.hidden===false",
            timeout=10000)
        self.assertEqual(self.page.locator("#stickyCopyNext").count(),1)
        self.assertTrue(self.page.locator("#stickyCopyNext").is_visible())
        self.page.locator("#detail").evaluate("(el)=>el.scrollTop=0")
        self.page.wait_for_function(
            "() => document.querySelector('#stickyAction')?.hidden===true",
            timeout=10000)

    def test_lean_ui_skips_only_empty_briefing_but_keeps_proof_and_warning(self):
        # Source-free synthetic visual dedup, never business readiness signoff.
        doc=fixture_document("2026-10-26T11:00:00Z")
        # No briefing in this valid snapshot: an empty shell must not appear.
        # Invalid empty dicts are covered only by pure presentation unit tests;
        # real ingestion must continue to reject malformed briefing payloads.
        self.snapshot.write_text(json.dumps(doc),encoding="utf-8")
        self.desk.import_snapshot()
        self.page.reload(wait_until="domcontentloaded")
        self.choose("CCON-1")
        self.assertEqual(self.page.locator("#detail .ba-brief").count(),0)
        self.assertEqual(self.page.locator("#nextText").count(),1)
        diagnostics=self.page.locator("#countDetails").text_content()
        self.assertNotIn("короткі кандидати", diagnostics)
        self.assertIn("аналіз:", diagnostics)

        doc["generatedAt"]="2026-10-26T11:01:00Z"
        doc["tasks"][0]["analysis"]["briefing"]={
            "overviewUk":"Synthetic source review needed",
            "currentUk":"Synthetic REST includes an unwanted segment",
            "targetUk":"Synthetic REST must exclude the segment under test",
            "businessImpactUk":"Synthetic BA acceptance is pending",
            "technicalScopeUk":"Synthetic endpoint only",
            "readiness":"NEEDS_CONFIRMATION",
            "readinessReasonUk":"Source review and manual signoff needed",
            "sourceAudit":[{"descriptionUk":"Synthetic source trace",
                            "status":"READ","sourceUrl":"https://example.invalid/source"}],
            "confirmedFacts":[{"textUk":"Synthetic fact","sourceUrl":"https://example.invalid/source"}],
            "timeline":[],
            "rules":[{"whenUk":"Synthetic A","thenUk":"Synthetic B",
                      "certainty":"OPEN","sourceUrl":"https://example.invalid/rule"}],
            "verification":[{"scenarioUk":"Synthetic A","expectedUk":"Synthetic B",
                             "sourceUrl":"https://example.invalid/rule"}],
            "unknownsUk":["Supplier reply still needed"],
            "risksUk":["Synthetic risk requires BA verification"]
        }
        self.snapshot.write_text(json.dumps(doc),encoding="utf-8")
        self.desk.import_snapshot()
        self.page.reload(wait_until="domcontentloaded")
        self.choose("CCON-1")
        self.assertEqual(self.page.locator("#detail .ba-brief").count(),1)
        self.assertIn("Є відкриті рішення",self.page.locator(".ba-brief").inner_text())
        self.page.locator(".ba-brief details").filter(has_text="Правила IF / THEN").locator("summary").click()
        self.assertIn("Synthetic A",self.page.locator(".ba-brief").inner_text())
        self.assertIn("Synthetic B",self.page.locator(".ba-brief").inner_text())
        self.page.locator(".ba-brief details").filter(has_text="Що не встановлено").locator("summary").click()
        self.assertIn("Supplier reply still needed",self.page.locator(".ba-brief").inner_text())
        self.assertEqual(self.page.locator("#copyNext").count(),1)

        doc["generatedAt"]="2026-10-26T11:02:00Z"
        doc["tasks"][0].pop("analysis")
        self.snapshot.write_text(json.dumps(doc),encoding="utf-8")
        self.desk.import_snapshot()
        self.page.reload(wait_until="domcontentloaded")
        self.choose("CCON-1")
        self.assertEqual(self.page.locator("#detail .ba-brief").count(),0)
        self.assertEqual(self.page.locator("#detail .analysis-missing").filter(has_text="Для цієї задачі ще немає повного аналізу").count(),1)
        self.assertNotIn("Поки не визначено — потрібен аналіз контексту.",
                         self.page.locator("#detail").inner_text())
        self.assertEqual(self.page.locator("#questionTracker").count(),1)

    def test_long_technical_pnr_rest_rules_and_repeatable_viewport_snapshots(self):
        # UI-08/UI-10 synthetic geometry and same-content pixel repeatability.
        # This does not replace a reviewed cross-commit visual baseline.
        pnr="LONGPNR" + "ZX97YJ" * 35
        condition="Order/SegmentRefID/" + pnr + "/DeliveryStatusCode=REMOVED"
        outcome="DoNotReturn/" + pnr + "/REST.RS.segment"
        doc=fixture_document("2026-10-26T11:30:00Z")
        doc["tasks"][0]["analysis"]["briefing"]={
            "overviewUk":"Synthetic IF/THEN source review",
            "currentUk":"Synthetic API returns a segment",
            "targetUk":"Synthetic API must exclude segment under condition",
            "businessImpactUk":"Synthetic test only",
            "technicalScopeUk":"REST Read PNR / Booking response",
            "readiness":"NEEDS_CONFIRMATION",
            "readinessReasonUk":"Requires independent QA and supplier proof",
            "sourceAudit":[],
            "confirmedFacts":[],
            "timeline":[],
            "rules":[{"whenUk":condition,"thenUk":outcome,"certainty":"OPEN",
                      "sourceUrl":"https://example.invalid/technical"}],
            "verification":[],
            "unknownsUk":["Synthetic long token requires visual review"],
            "risksUk":[]
        }
        self.snapshot.write_text(json.dumps(doc),encoding="utf-8")
        self.desk.import_snapshot()
        signatures={}
        for width,height in ((320,850),(768,900),(1440,900)):
            self.page.set_viewport_size({"width":width,"height":height})
            self.page.reload(wait_until="domcontentloaded")
            self.choose("CCON-1")
            rule=self.page.locator(".ba-brief details").filter(
                has_text="Правила IF / THEN").first
            if not rule.evaluate("(node)=>node.open"):
                rule.locator("summary").click()
            self.page.locator(".ba-brief .technical-token").first.wait_for()
            values=self.page.locator(".ba-brief .technical-token").all_text_contents()
            self.assertEqual(values,[condition,outcome])
            geometry=self.page.evaluate("""() => {
                const tokens=[...document.querySelectorAll('.ba-brief .technical-token')];
                return {
                    viewport:document.documentElement.clientWidth,
                    document:document.documentElement.scrollWidth,
                    tokens:tokens.map(el=>({
                        overflowWrap:getComputedStyle(el).overflowWrap,
                        whiteSpace:getComputedStyle(el).whiteSpace,
                        scrollWidth:el.scrollWidth,
                        clientWidth:el.clientWidth
                    }))
                };
            }""")
            self.assertLessEqual(geometry["document"],geometry["viewport"]+2,geometry)
            for token in geometry["tokens"]:
                self.assertEqual(token["overflowWrap"],"anywhere")
                self.assertEqual(token["whiteSpace"],"pre-wrap")
            # Pointer/focus and the transient sticky action are not part of
            # the static source panel being compared.
            # The app correctly restores per-task disclosure state from
            # sessionStorage. A screenshot must use a fixed panel state so
            # that the difference test measures rendering, not user choices.
            self.page.evaluate("""() => {
                for(const node of document.querySelectorAll('.ba-brief details')) {
                    const label=node.querySelector('summary')?.textContent || '';
                    node.open=label.includes('Правила IF / THEN');
                }
                document.activeElement?.blur();
            }""")
            self.page.mouse.move(0,0)
            # Geometry/semantic snapshot is stable despite native raster
            # noise. Keep *both* PNGs as evidence for a future approved
            # cross-version human pixel-baseline comparison.
            capture_layout="""() => {
                const root=document.querySelector('.ba-brief');
                const box=root.getBoundingClientRect();
                const tokens=[...root.querySelectorAll('.technical-token')];
                return {
                    text:root.textContent,
                    width:Math.round(box.width),
                    height:Math.round(box.height),
                    openSections:[...root.querySelectorAll('details')]
                        .map(d=>d.open),
                    tokenWidths:tokens.map(node=>Math.round(
                        node.getBoundingClientRect().width)),
                    tokenTexts:tokens.map(node=>node.textContent)
                };
            }"""
            before=self.page.evaluate(capture_layout)
            screenshot_style="#stickyAction{visibility:hidden!important}"
            first=self.page.locator(".ba-brief").screenshot(
                animations="disabled",style=screenshot_style)
            (ARTIFACTS/f"synthetic-technical-long-{width}-before.png").write_bytes(first)
            self.page.reload(wait_until="domcontentloaded")
            self.choose("CCON-1")
            rule=self.page.locator(".ba-brief details").filter(
                has_text="Правила IF / THEN").first
            if not rule.evaluate("(node)=>node.open"):
                rule.locator("summary").click()
            self.page.evaluate("""() => {
                for(const node of document.querySelectorAll('.ba-brief details')) {
                    const label=node.querySelector('summary')?.textContent || '';
                    node.open=label.includes('Правила IF / THEN');
                }
                document.activeElement?.blur();
            }""")
            self.page.mouse.move(0,0)
            after=self.page.evaluate(capture_layout)
            self.assertEqual(before["text"],after["text"],
                             f"technical source text changed at {width}px")
            self.assertEqual(before["openSections"],after["openSections"])
            self.assertEqual(before["tokenTexts"],after["tokenTexts"])
            for key in ("width","height"):
                self.assertLessEqual(abs(before[key]-after[key]),2,
                                     f"visual {key} changed at {width}px")
            for left,right in zip(before["tokenWidths"],after["tokenWidths"]):
                self.assertLessEqual(abs(left-right),2,
                                     f"token width changed at {width}px")
            second=self.page.locator(".ba-brief").screenshot(
                animations="disabled",style=screenshot_style)
            (ARTIFACTS/f"synthetic-technical-long-{width}-after.png").write_bytes(second)
            signatures[str(width)]={
                "semanticLayoutStable":True,
                "beforeSha256":hashlib.sha256(first).hexdigest(),
                "afterSha256":hashlib.sha256(second).hexdigest(),
                "beforeDimensions":{k:before[k] for k in ("width","height")},
                "afterDimensions":{k:after[k] for k in ("width","height")}
            }
            self.page.screenshot(path=str(ARTIFACTS/
                f"synthetic-technical-long-{width}.png"),full_page=True)
        ARTIFACTS.joinpath("synthetic-technical-visual-hashes.json").write_text(
            json.dumps({"syntheticOnly":True,"semanticGeometryRegression":True,
                        "pixelHashesInformational":True,
                        "notAnApprovedCrossVersionPixelBaseline":True,
                        "snapshotsByViewport":signatures},
                       indent=2),encoding="utf-8")

    def test_three_viewports_and_short_soak_no_external_writes(self):
        self.choose("CCON-2")
        for width,height in [(320,800),(768,900),(1440,900)]:
            self.page.set_viewport_size({"width":width,"height":height})
            self.assertTrue(self.page.locator("#save").count()==1)
            self.assertTrue(self.page.locator("#note").is_visible())
            self.assertTrue(self.page.locator("#detail").is_visible())
        self.page.set_viewport_size({"width":1280,"height":820})
        timings=[]
        for index in range(90):
            key=("CCON-1","CCON-2","CCON-3")[index%3]
            started=time.perf_counter()
            self.page.locator(f'#list button[data-key="{key}"]').click()
            timings.append((time.perf_counter()-started)*1000)
        self.assertEqual(self.page.locator("#list button[data-key]").count(),3)
        self.timings.append({
            "scenario":"90 DOM-backed click/selection transitions",
            "p50Ms":round(statistics.median(timings),2),
            "maxMs":round(max(timings),2),"syntheticOnly":True
        })


if __name__=="__main__":
    unittest.main(verbosity=2)
