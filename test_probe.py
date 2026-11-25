import copy
import io
import json
import unittest
from unittest.mock import patch

import probe


def fixture():
    return {'updated': '2026-11-25T01:46:22.630Z', 'efforts': [], 'tools': [],
            'candidates': [], 'ignored': [], 'flagged': []}


class FakeResponse(io.BytesIO):
    def __init__(self, body, url, media_type='application/json'):
        super().__init__(body)
        self.status = 200
        self.url = url
        self.headers = {'Content-Type': media_type}

    def geturl(self):
        return self.url


class ProbeTests(unittest.TestCase):
    def test_valid_response(self):
        body = json.dumps(fixture()).encode()
        with patch('probe.urlopen', return_value=FakeResponse(body, probe.LIVE)):
            meta, data = probe.fetch(probe.LIVE)
        self.assertTrue(meta['ok'])
        self.assertEqual(meta['status'], 200)
        self.assertEqual(data, fixture())

    def test_html_is_not_registry(self):
        with patch('probe.urlopen', return_value=FakeResponse(b'<html>Error</html>', probe.LIVE, 'text/html')):
            meta, data = probe.fetch(probe.LIVE)
        self.assertFalse(meta['ok'])
        self.assertIsNone(data)

    def test_bad_schema(self):
        with patch('probe.urlopen', return_value=FakeResponse(b'{"updated":"2026-11-25T01:46:22Z"}', probe.LIVE)):
            meta, data = probe.fetch(probe.LIVE)
        self.assertFalse(meta['ok'])
        self.assertIsNone(data)

    def test_wrong_final_host(self):
        with patch('probe.urlopen', return_value=FakeResponse(json.dumps(fixture()).encode(), 'https://example.com/data/tracker.json')):
            meta, data = probe.fetch(probe.LIVE)
        self.assertFalse(meta['ok'])
        self.assertIsNone(data)

    def test_normalized_match_and_mismatch(self):
        source = fixture()
        source['site'] = {'url': probe.OLD_ORIGIN}
        live = copy.deepcopy(source)
        live['site']['url'] = probe.NEW_ORIGIN
        self.assertEqual(probe.canonical(live), probe.canonical(source))
        live['candidates'].append({'repo': 'tudorek12345/Leonida'})
        self.assertNotEqual(probe.canonical(live), probe.canonical(source))

    def test_related_and_flag_reason(self):
        data = fixture()
        data['efforts'] = [{'repo': 'other/repo', 'relatedRepos': [{'repo': 'TUDOREK12345/Leonida'}]}]
        data['flagged'] = [{'reason': 'example reason', 'members': [{'repo': 'tudorek12345/VictoryIsInOurName.hep'}, {'repo': 'other/repo'}]}]
        found = probe.matching_entries(data)
        self.assertEqual([x['category'] for x in found], ['efforts', 'flagged'])
        self.assertEqual(found[1]['reason'], 'example reason')
        self.assertEqual(len(found[1]['matching_members']), 1)

    def test_failure_never_matches(self):
        meta = {'ok': False, 'sha256': None}
        e = probe.build_evidence(meta, None, meta, None)
        self.assertFalse(e['matches_current_source'])
        self.assertIsNone(e['live_matches'])
        self.assertIsNone(e['byte_identical'])


if __name__ == '__main__':
    unittest.main()
