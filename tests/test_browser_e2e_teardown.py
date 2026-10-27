"""Synthetic check: tearDown screenshots use unittest recorded failures."""
import unittest
from types import SimpleNamespace
from browser_e2e import recorded_failure

class BrowserFailureDetectionTests(unittest.TestCase):
    def test_recorded_failure_does_not_depend_on_transient_success_flag(self):
        case=object()
        other=object()
        result=SimpleNamespace(failures=[(case,"trace")],errors=[])
        self.assertTrue(recorded_failure(result,case))
        self.assertFalse(recorded_failure(result,other))
        self.assertFalse(recorded_failure(None,case))
        result=SimpleNamespace(failures=[],errors=[(case,"error")])
        self.assertTrue(recorded_failure(result,case))
