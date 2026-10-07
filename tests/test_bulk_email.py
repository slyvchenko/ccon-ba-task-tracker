import unittest
from unittest.mock import Mock, patch
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import Request, build_opener, ProxyHandler
from urllib.parse import urlparse, parse_qs
from server import open_email_batch, handler

class BulkEmailTests(unittest.TestCase):
    def item(self, key='CCON-1'):
        return {'key':key, 'draft':{'to':'Team <one@example.com>, Other <two@example.com>', 'subject':'AER. Test [1]', 'body':'Dear Team,\n\nQuestion?'}}

    def test_opens_each_draft_with_names_parsed(self):
        opener=Mock()
        result=open_email_batch([self.item(),self.item('CCON-2')],opener)
        self.assertEqual(result,{'opened':['CCON-1','CCON-2'],'failed':[]})
        self.assertEqual(opener.call_count,2)
        url=opener.call_args_list[0].args[0]
        self.assertTrue(url.startswith('mailto:one@example.com,two@example.com?'))
        self.assertEqual(parse_qs(urlparse(url).query)['body'][0],self.item()['draft']['body'])

    def test_invalid_batch_never_launches(self):
        opener=Mock(); invalid=self.item('CCON-2');invalid['draft']['to']=''
        with self.assertRaises(ValueError):open_email_batch([self.item(),invalid],opener)
        opener.assert_not_called()

    def test_duplicate_keys_rejected(self):
        opener=Mock()
        with self.assertRaises(ValueError):open_email_batch([self.item(),self.item()],opener)
        opener.assert_not_called()

    def test_partial_failure_reported(self):
        opener=Mock(side_effect=[OSError(),None])
        self.assertEqual(open_email_batch([self.item(),self.item('CCON-2')],opener),{'opened':['CCON-2'],'failed':['CCON-1']})

    def test_header_injection_rejected(self):
        item=self.item();item['draft']['subject']='Test\nBcc: other@example.com'
        with self.assertRaises(ValueError):open_email_batch([item],Mock())

    def test_empty_batch_rejected(self):
        with self.assertRaises(ValueError):open_email_batch([],Mock())

    def test_http_batch_handoff(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),handler(None))
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        origin=f'http://127.0.0.1:{server.server_port}'
        request=Request(origin+'/api/email/open-batch',data=json.dumps({'items':[self.item()]}).encode(),headers={'Origin':origin,'Content-Type':'application/json'})
        try:
            with patch('server.os.startfile',create=True) as launch:
                with build_opener(ProxyHandler({})).open(request) as response:
                    self.assertEqual(json.load(response),{'opened':['CCON-1'],'failed':[]})
                launch.assert_called_once()
        finally:
            server.shutdown();server.server_close();thread.join()

