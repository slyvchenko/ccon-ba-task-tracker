"""Synthetic QA-08 tests: model-bound payloads never contain these test secrets."""
import json
import unittest

from model_analysis import request_analysis, sanitize_source
from prompt_safety import sensitive_key, strip_sensitive_text


class PromptSafetyTests(unittest.TestCase):
    def test_camelcase_header_and_nested_secret_fields_are_dropped(self):
        source = {"issue": {
            "summary": "Check TypeCode=TO and SegmentRefID",
            "accessToken": "fakeACCESSvalue", "clientSecret": "fakeCLIENTvalue",
            "X-API-Key": "fakeHEADERvalue", "session_id": "fakeSESSIONvalue",
            "headers": [{"AuthorizationHeader": "fakeBEARERvalue"}],
            "technical": {"TypeCode": "TO", "SegmentRefID": "SEG1",
                          "fareComponent": "FC1"},
        }}
        result = sanitize_source(source)
        dump = json.dumps(result)
        for marker in ("fakeACCESSvalue", "fakeCLIENTvalue", "fakeHEADERvalue",
                       "fakeSESSIONvalue", "fakeBEARERvalue"):
            self.assertNotIn(marker, dump)
        self.assertEqual(result["issue"]["technical"]["TypeCode"], "TO")
        self.assertEqual(result["issue"]["technical"]["SegmentRefID"], "SEG1")
        self.assertFalse(sensitive_key("TypeCode"))
        self.assertTrue(sensitive_key("refreshToken"))
        self.assertTrue(sensitive_key("x_api_key"))

    def test_urls_strip_query_fragment_and_embedded_credentials(self):
        value = (
            "Read https://jira.example/browse/CCON-7?session=syntheticSecret#fragment "
            "and https://tester:syntheticPass@files.example/private.pdf "
            "and https://logs.example/flow/ccon-17?flowId=customer-id."
        )
        safe = strip_sensitive_text(value)
        self.assertIn("https://jira.example/browse/CCON-7", safe)
        self.assertIn("https://logs.example/flow/ccon-17", safe)
        for marker in ("syntheticSecret", "syntheticPass", "customer-id", "#fragment"):
            self.assertNotIn(marker, safe)
        self.assertIn("[REDACTED_URL]", safe)

    def test_emails_phones_explicit_secrets_and_private_key_removed(self):
        source = ("Contact analyst.qa@example.test by phone +48123456789; "
                  "tel: 123 456 789; sessionId=syntheticSession123 "
                  "github_pat_" + "A" * 20 + " "
                  "-----BEGIN PRIVATE KEY-----\nsecretData\n-----END PRIVATE KEY-----")
        safe = sanitize_source({"description": source})["description"]
        for marker in ("analyst.qa@example.test", "+48123456789",
                       "123 456 789", "secretData", "syntheticSession123",
                       "github_pat_"):
            self.assertNotIn(marker, safe)
        self.assertIn("[REDACTED_EMAIL]", safe)
        self.assertIn("[REDACTED_PRIVATE_KEY]", safe)

    def test_model_request_data_is_scrubbed_before_approved_transport(self):
        captured = []
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, limit):
                return b'{"choices":[{"message":{"content":"{}"}}]}'
        def opener(request, timeout):
            captured.append(json.loads(request.data))
            return Response()
        context = {"issue": {
            "key": "CCON-7", "description": "Fetch https://jira.example/browse/CCON-7?sessionId=private123",
            "headers": {"x-api-key": "notForModel"}, "technical": {"TypeCode": "TO"},
        }}
        settings = {"model": "synthetic", "endpoint": "https://approved.example/v1/chat/completions",
                    "key": "transient-test-key"}
        with self.assertRaises(ValueError):
            request_analysis(settings, "Approved rules", context,
                             note="Contact test@example.org", opener=opener)
        self.assertEqual(len(captured), 1)
        contents = captured[0]["messages"]
        self.assertEqual(contents[0]["role"], "system")
        self.assertEqual(contents[1]["role"], "user")
        payload = contents[1]["content"]
        for marker in ("private123", "notForModel", "test@example.org"):
            self.assertNotIn(marker, payload)
        self.assertIn("TypeCode", payload)


if __name__ == "__main__":
    unittest.main()
