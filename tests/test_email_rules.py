import unittest
from email_rules import normalize_draft

class EmailRules(unittest.TestCase):
    def test_user_example_and_idempotency(self):
        draft={'to':'','subject':'CCON-15344 — verify-fare: success=false without an error message','body':'Hi Airtuerk team,\n\nQuestion?\n\nWe will add the relevant request ID, timestamp and response excerpt from the linked logs before sending.\n\nBest regards,\nVolodymyr'}
        result=normalize_draft('CCON-15344',draft)
        self.assertEqual(result['subject'],'AER. verify-fare. Success=false without an error message [15344]')
        self.assertEqual(result['body'],'Dear Team,\n\nQuestion?\n\nLogs attached for your reference.')
        self.assertEqual(normalize_draft('CCON-15344',result),result)

    def test_no_email_remains_empty(self):
        draft={'to':'','subject':'','body':''}
        self.assertEqual(normalize_draft('CCON-1',draft),draft)
