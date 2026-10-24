import os
import unittest
from unittest.mock import patch

from jira_sync import query_for_owner, JQL
from priority_score import FACTORS, validate_priority_factors, factor_summary
from schema import validate_analysis


class PersonalScopeAndScoringTests(unittest.TestCase):
    def test_local_defaults_to_my_current_jira_user(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(query_for_owner(), JQL)
            self.assertIn("assignee = currentUser()", JQL)

    def test_cloud_requires_exact_user_id_not_service_account(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "requires CCON_JIRA_ASSIGNEE_ACCOUNT_ID"):
                query_for_owner(cloud_mode=True)
            result = query_for_owner("557058:abcd0123", cloud_mode=True)
            self.assertIn('assignee = "557058:abcd0123"', result)
            self.assertNotIn("currentUser()", result)
            self.assertIn("project = CCON", result)
            with self.assertRaises(ValueError):
                query_for_owner('abc" OR project=SECRET', cloud_mode=True)

    def test_sum_of_factors_yields_valid_total(self):
        factors = {
            "businessImpact": 25, "urgency": 12,
            "dependencies": 18, "baDecision": 10,
            "actionability": 8,
        }
        self.assertEqual(validate_priority_factors(factors, 73), 73)
        self.assertEqual(factor_summary(factors)["max"], 100)
        validate_analysis({"queueScore": 73, "priorityFactors": factors})
        with self.assertRaisesRegex(ValueError, "must equal"):
            validate_analysis({"queueScore": 74, "priorityFactors": factors})

    def test_factor_validation_catches_boundary_and_boolean_errors(self):
        allmax = {key: maximum for key, maximum in FACTORS.items()}
        self.assertEqual(validate_priority_factors(allmax), 100)
        allzero = {key: 0 for key in FACTORS}
        self.assertEqual(validate_priority_factors(allzero), 0)
        for wrong in (True, -1, 26, 1.5):
            factors = dict(allzero, businessImpact=wrong)
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                validate_priority_factors(factors)

    def test_legacy_scores_remain_compatible(self):
        validate_analysis({"queueScore": 80})
        validate_analysis({"signal": "REVIEW", "queueScore": 0})


if __name__ == "__main__":
    unittest.main()
