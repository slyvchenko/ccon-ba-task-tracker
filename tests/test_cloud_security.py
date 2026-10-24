import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

from cloud_security import cloud_configuration, authorized
from desk_store import Desk
from server import handler


class TrustedCloudGatewayTests(unittest.TestCase):
    def setUp(self):
        self.cfg = cloud_configuration({
            "CCON_CLOUD_MODE": "1",
            "CCON_PUBLIC_ORIGIN": "https://ba.example.test",
            "CCON_AUTHORIZED_EMAIL": "me@example.test",
            "CCON_PROXY_SHARED_SECRET": "a" * 64,
        })

    def test_cloud_configuration_requires_validated_https_and_long_secret(self):
        self.assertEqual(self.cfg["netloc"], "ba.example.test")
        with self.assertRaises(ValueError):
            cloud_configuration({
                "CCON_CLOUD_MODE": "1",
                "CCON_PUBLIC_ORIGIN": "http://ba.example.test",
                "CCON_AUTHORIZED_EMAIL": "me@example.test",
                "CCON_PROXY_SHARED_SECRET": "a" * 64,
            })

    def test_identity_and_proxy_secret_are_both_required(self):
        headers = {
            "Host": "ba.example.test",
            "X-CCON-Proxy-Secret": "a" * 64,
            "X-CCON-Verified-Email": "me@example.test",
        }
        self.assertTrue(authorized(headers, self.cfg))
        self.assertFalse(authorized({**headers, "X-CCON-Proxy-Secret": "wrong"}, self.cfg))
        self.assertFalse(authorized({**headers, "X-CCON-Verified-Email": "other@example.test"}, self.cfg))
        self.assertFalse(authorized({**headers, "Host": "attacker.example.test"}, self.cfg))
        self.assertFalse(authorized({**headers, "Origin": "https://evil.test"}, self.cfg, "POST"))
        self.assertTrue(authorized({**headers, "Origin": self.cfg["origin"]}, self.cfg, "POST"))

    def test_http_api_and_static_assets_do_not_bypass_auth(self):
        with tempfile.TemporaryDirectory(prefix="ccon-auth-") as folder:
            desk = Desk(Path(folder))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler(desk, self.cfg))
            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()
            url = f"http://127.0.0.1:{server.server_port}"
            opener = build_opener(ProxyHandler({}))
            good = {
                "Host": "ba.example.test",
                "X-CCON-Proxy-Secret": "a" * 64,
                "X-CCON-Verified-Email": "me@example.test",
            }
            try:
                for path in ("/", "/api/health", "/api/tasks", "/api/export",
                             "/api/logs", "/api/daily-report"):
                    with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                        opener.open(Request(url + path), timeout=3)
                    self.assertEqual(error.exception.code, 403)
                with opener.open(Request(url + "/api/health", headers=good)) as response:
                    self.assertEqual(json.load(response)["app"], "CCON BA Desk")
                post = Request(url + "/api/import", data=b"{}", method="POST",
                               headers={**good, "Origin": self.cfg["origin"],
                                        "Content-Type": "application/json"})
                with self.assertRaises(HTTPError) as error:
                    opener.open(post, timeout=3)
                self.assertEqual(error.exception.code, 403)
            finally:
                server.shutdown()
                server.server_close()
                t.join()


if __name__ == "__main__":
    unittest.main()
