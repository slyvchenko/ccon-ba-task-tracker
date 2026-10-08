import unittest
from email_rules import normalize_draft

class EmailRules(unittest.TestCase):
    def test_verified_supplier_method_in_generated_subject_and_template(self):
        draft={'to':'','subject':'AER. retrievePNR. Invalid record locator [15340]',
               'body':'Dear Team,\n\nWe have recently received the following error during retrievePNR:\nInvalid record locator\n\nCould you please investigate?'}
        result=normalize_draft('CCON-15340',draft,'doByLocatorPullPnr')
        self.assertEqual(result['subject'],'AER. doByLocatorPullPnr. Invalid record locator [15340]')
        self.assertIn('during doByLocatorPullPnr:',result['body'])
        self.assertEqual(normalize_draft('CCON-15340',result,'doByLocatorPullPnr'),result)

    def test_user_example_and_idempotency(self):
        draft={'to':'','subject':'CCON-15344 — verify-fare: success=false without an error message','body':'Hi Airtuerk team,\n\nQuestion?\n\nWe will add the relevant request ID, timestamp and response excerpt from the linked logs before sending.\n\nBest regards,\nVolodymyr'}
        result=normalize_draft('CCON-15344',draft)
        self.assertEqual(result['subject'],'AER. verify-fare. Success=false without an error message [15344]')
        self.assertEqual(result['body'],'Dear Team,\n\nQuestion?\n\nLogs are attached for your reference.\nThanks in advance for your endless support.')
        self.assertEqual(normalize_draft('CCON-15344',result),result)

    def test_no_email_remains_empty(self):
        draft={'to':'','subject':'','body':''}
        self.assertEqual(normalize_draft('CCON-1',draft),draft)

    def test_detailed_letter_and_situational_thanks_preserved(self):
        content='The retry failed again.\n\n1. Has the upstream fix been deployed?\n2. Which recovery is safe?'
        draft={'to':'','subject':'AER. bookings. Follow-up [1]','body':'Dear Team,\n\n'+content+'\n\nLogs are attached for your reference.\nThanks for your continued support with this issue.'}
        result=normalize_draft('CCON-1',draft)
        self.assertIn(content,result['body'])
        self.assertEqual(result['body'].count('Logs are attached for your reference.'),1)
        self.assertTrue(result['body'].endswith('Thanks for your continued support with this issue.'))
        self.assertEqual(normalize_draft('CCON-1',result),result)
