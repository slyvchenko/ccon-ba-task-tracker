"""Synthetic, local HTTP only. No real Jira/network telemetry or task identifiers."""
import json
import socket
import time
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import build_opener, ProxyHandler

from desk_store import Desk
from local_error_budget import LocalErrorBudget
from server import handler


class ErrorBudgetUnitTests(unittest.TestCase):
    def test_bounded_rolling_aggregates_only(self):
        moment=[1000]
        budget=LocalErrorBudget(clock=lambda:moment[0], window_seconds=60, max_samples=20)
        budget.record("/api/history/CCON-555?secret=PRIVATE-TOKEN", 200, 23.6)
        budget.record("/api/tasks/CCON-999", 503, 199)
        budget.record("/api/tasks/CCON-888", 409, 44)
        budget.record("/api/health", 500, 300)
        budget.record("/api/error-budget", 500, 300)
        budget.record("/local-error-budget", 500, 300)
        snap=budget.snapshot()
        self.assertEqual((snap["sampledApiResponses"],snap["server5xx"],snap["client4xx"]),
                         (3,1,1))
        self.assertEqual(snap["successPercent"],66.67)
        self.assertTrue(snap["insufficientSamples"])
        self.assertFalse(snap["remoteTelemetry"])
        self.assertEqual(snap["errorBudgetUsed"],1)
        self.assertTrue(snap["noFullAvailabilityClaim"])
        for private in ("CCON-555","CCON-999","PRIVATE-TOKEN","/api/history"):
            self.assertNotIn(private,json.dumps(snap))
        moment[0]=1061
        self.assertEqual(budget.snapshot()["sampledApiResponses"],0)
        self.assertIsNone(budget.snapshot()["successPercent"])

    def test_sampling_cap_warns_and_does_not_store_paths(self):
        b=LocalErrorBudget(max_samples=20)
        for _ in range(25):
            b.record("/api/logs/CCON-123/private",200,1)
        result=b.snapshot()
        self.assertEqual(result["sampledApiResponses"],20)
        self.assertTrue(result["sampleTruncated"])
        self.assertEqual(result["server5xx"],0)
        for args in [("/api/any",0,1),("/api/any",610,1)]:
            b.record(*args)
        self.assertEqual(b.snapshot()["sampledApiResponses"],20)

    def test_truncation_warning_expires_with_rolling_window(self):
        now=[1000]
        budget=LocalErrorBudget(clock=lambda:now[0], window_seconds=60, max_samples=20)
        for _ in range(25):
            budget.record("/api/tasks",200,1)
        self.assertTrue(budget.snapshot()["sampleTruncated"])
        now[0]+=61
        self.assertFalse(budget.snapshot()["sampleTruncated"])
        self.assertEqual(budget.snapshot()["sampledApiResponses"],0)
        for _ in range(19):
            budget.record("/api/tasks",200,1)
        self.assertFalse(budget.snapshot()["sampleTruncated"])

    def test_status_is_an_observation_not_an_availability_guarantee(self):
        b=LocalErrorBudget()
        self.assertIsNone(b.snapshot()["serverTimeToStatusP95Ms"])
        self.assertIn("HTTP statuses", b.snapshot()["scope"])
        with self.assertRaises(ValueError):
            LocalErrorBudget(max_samples=1)


class LocalEndpointTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix="ccon-error-budget-synthetic-")
        self.addCleanup(temporary.cleanup)
        self.desk=Desk(Path(temporary.name))
        self.budget=LocalErrorBudget()
        self.http=ThreadingHTTPServer(("127.0.0.1",0),
                                     handler(self.desk, error_budget=self.budget))
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.finish)
        self.base=f"http://127.0.0.1:{self.http.server_port}"
        self.opener=build_opener(ProxyHandler({}))

    def finish(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=3)

    def get(self, path):
        with self.opener.open(self.base+path,timeout=5) as response:
            return response.status,response.headers["Content-Type"],response.read()

    def test_opt_in_dashboard_counts_only_real_local_api_responses(self):
        status,mime,payload=self.get("/local-error-budget")
        self.assertEqual(status,200)
        self.assertIn("text/html",mime)
        self.assertIn(b"error-budget.mjs",payload)
        self.get("/api/tasks/revision")
        with self.assertRaises(HTTPError) as missing:
            self.get("/api/private/CCON-456")
        self.assertEqual(missing.exception.code,404)
        self.get("/api/health")
        self.get("/assets/error-budget.mjs")
        _,_,response=self.get("/api/error-budget")
        result=json.loads(response)
        self.assertEqual(result["sampledApiResponses"],2)
        self.assertEqual(result["client4xx"],1)
        self.assertEqual(result["server5xx"],0)
        self.assertNotIn("CCON-456",json.dumps(result))
        self.assertEqual(self.desk.revision()["revision"],0)

    def test_base_handler_unsupported_method_is_counted_once(self):
        from urllib.request import Request
        with self.assertRaises(HTTPError) as error:
            self.opener.open(Request(self.base+"/api/tasks/CCON-123",
                                     data=b"{}",method="PUT"),timeout=5)
        self.assertEqual(error.exception.code,501)
        report=self.budget.snapshot()
        self.assertEqual(report["sampledApiResponses"],1)
        self.assertEqual(report["server5xx"],1)
        self.assertEqual(report["client4xx"],0)

    def test_idle_tcp_connection_does_not_inflate_server_latency(self):
        with socket.create_connection(("127.0.0.1",self.http.server_port),
                                      timeout=5) as sock:
            # Idle before sending request line must not count as app latency.
            time.sleep(.65)
            raw=(f"GET /api/tasks/revision HTTP/1.1\r\n"
                 f"Host: 127.0.0.1:{self.http.server_port}\r\n"
                 "Connection: close\r\n\r\n")
            sock.sendall(raw.encode("ascii"))
            sock.settimeout(5)
            received=b""
            while True:
                chunk=sock.recv(4096)
                if not chunk:
                    break
                received+=chunk
        self.assertIn(b" 200 OK",received)
        observed=self.budget.snapshot()
        self.assertEqual(observed["sampledApiResponses"],1)
        self.assertLess(observed["serverTimeToStatusP95Ms"],450)

    def test_disabled_and_cloud_mode_never_expose_diagnostics(self):
        server=ThreadingHTTPServer(("127.0.0.1",0),handler(self.desk))
        th=threading.Thread(target=server.serve_forever,daemon=True);th.start()
        try:
            url=f"http://127.0.0.1:{server.server_port}"
            for path in ("/api/error-budget","/local-error-budget"):
                with self.assertRaises(HTTPError) as exc:
                    self.opener.open(url+path,timeout=5)
                self.assertEqual(exc.exception.code,404)
        finally:
            server.shutdown();server.server_close();th.join(timeout=3)
        # Local opt-in must be discarded for trusted-cloud handler construction.
        from cloud_security import cloud_configuration
        cfg=cloud_configuration({
            "CCON_CLOUD_MODE":"1","CCON_PUBLIC_ORIGIN":"https://ba.example.test",
            "CCON_AUTHORIZED_EMAIL":"me@example.test",
            "CCON_PROXY_SHARED_SECRET":"a"*64})
        cloudserver=ThreadingHTTPServer(("127.0.0.1",0),
                            handler(self.desk,cfg,error_budget=self.budget))
        th=threading.Thread(target=cloudserver.serve_forever,daemon=True);th.start()
        headers={"Host":"ba.example.test","X-CCON-Proxy-Secret":"a"*64,
                 "X-CCON-Verified-Email":"me@example.test"}
        try:
            from urllib.request import Request
            url=f"http://127.0.0.1:{cloudserver.server_port}"
            with self.assertRaises(HTTPError) as exc:
                self.opener.open(Request(url+"/api/error-budget",headers=headers),timeout=5)
            self.assertEqual(exc.exception.code,404)
        finally:
            cloudserver.shutdown();cloudserver.server_close();th.join(timeout=3)


if __name__=="__main__":
    unittest.main()
