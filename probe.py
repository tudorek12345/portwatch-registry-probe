"""Read-only HTTPS verification of the public PortWatch production registry."""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

LIVE = 'https://portwatch-vi.xyz/data/tracker.json'
SOURCE = 'https://raw.githubusercontent.com/4lwayz/portwatch-vi/main/data/tracker.json'
OLD_ORIGIN = 'https://4lwayz.github.io/portwatch-vi/'
NEW_ORIGIN = 'https://portwatch-vi.xyz/'
TARGETS = ('tudorek12345/VictoryIsInOurName.hep', 'tudorek12345/Leonida',
           'Windows D3D12 runtime integration', 'Heperkoo’s Leonida',
           "Heperkoo's Leonida", 'VIctory integration')
CATEGORIES = ('efforts', 'tools', 'candidates', 'ignored', 'flagged', 'flags',
              'related', 'relatedRepos', 'relatedRepositories', 'related_repositories')
MAX_BYTES = 5 * 1024 * 1024
OUTPUT = Path(__file__).resolve().parent / 'evidence' / 'latest.json'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def validate(data):
    if not isinstance(data, dict) or not isinstance(data.get('updated'), str):
        raise ValueError('Expected registry object with updated timestamp')
    stamp = datetime.fromisoformat(data['updated'].replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Registry timestamp has no timezone')
    for key in ('efforts', 'tools', 'candidates', 'ignored', 'flagged'):
        if not isinstance(data.get(key), list):
            raise ValueError(f'Missing or invalid registry array: {key}')
    return data


def normalized(data):
    # Mirror the actual upstream Pages deployment's public-URL rewrite.
    if isinstance(data, str):
        return data.replace(OLD_ORIGIN, NEW_ORIGIN)
    if isinstance(data, list):
        return [normalized(v) for v in data]
    if isinstance(data, dict):
        return {k.replace(OLD_ORIGIN, NEW_ORIGIN): normalized(v) for k, v in data.items()}
    return data


def canonical(data):
    return json.dumps(normalized(data), ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def find_hits(node, path=''):
    if isinstance(node, str):
        for target in TARGETS:
            if target.casefold() in node.casefold():
                yield {'path': path, 'target': target}
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from find_hits(value, f'{path}.{key}' if path else key)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from find_hits(value, f'{path}[{i}]')


def matching_entries(data):
    results = []
    for category in CATEGORIES:
        entries = data.get(category, [])
        if not isinstance(entries, list):
            continue
        for i, entry in enumerate(entries):
            path = f'{category}[{i}]'
            hits = list(find_hits(entry, path))
            if not hits:
                continue
            summary = {'category': category, 'path': path, 'matches': hits}
            if isinstance(entry, dict):
                for k in ('repo', 'name', 'id', 'label', 'pattern', 'reason',
                          'status', 'tier', 'score', 'assessedAt', 'assessedBy'):
                    if k in entry:
                        summary[k] = entry[k]
                if isinstance(entry.get('members'), list):
                    summary['matching_members'] = [m for m in entry['members']
                                                   if list(find_hits(m))]
            elif isinstance(entry, str):
                summary['value'] = entry
            results.append(summary)
    return results


def fetch(url, attempts=3):
    expected = urlsplit(url)
    meta = {'ok': False, 'requested_url': url, 'status': None,
            'final_url': None, 'content_type': None, 'bytes': None,
            'sha256': None, 'updated': None, 'error': None, 'checked_at': None}
    for attempt in range(attempts):
        # Reset all response-specific metadata on each retry.
        meta.update(status=None, final_url=None, content_type=None, bytes=None,
                    sha256=None, updated=None, error=None, checked_at=now())
        try:
            request = Request(url, headers={
                'User-Agent': 'PortWatch-Registry-Probe/1.0 (public read-only verification)',
                'Accept': 'application/json, text/plain;q=0.9',
                'Cache-Control': 'no-cache', 'Accept-Encoding': 'identity',
            })
            with urlopen(request, timeout=20) as response:
                meta['status'] = response.status
                meta['final_url'] = response.geturl()
                meta['content_type'] = response.headers.get('Content-Type', '')
                final = urlsplit(meta['final_url'])
                if (final.scheme, final.netloc, final.path) != (expected.scheme, expected.netloc, expected.path):
                    raise ValueError('Unexpected final URL')
                if response.status != 200:
                    raise ValueError(f'Expected HTTP 200, received {response.status}')
                if url == LIVE:
                    media_type = meta['content_type'].split(';')[0].strip().lower()
                    if media_type != 'application/json' and not media_type.endswith('+json'):
                        raise ValueError('Live response is not JSON content type')
                body = response.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES:
                    raise ValueError('Response exceeds 5 MiB safety limit')
                meta['bytes'] = len(body)
                meta['sha256'] = hashlib.sha256(body).hexdigest()
                data = validate(json.loads(body))
                canonical(data)  # rejects nonstandard NaN / Infinity values
                meta.update(ok=True, updated=data['updated'], error=None)
                return meta, data
        except HTTPError as exc:
            meta.update(status=exc.code, final_url=exc.geturl(),
                        content_type=exc.headers.get('Content-Type'), error=f'HTTP {exc.code}')
            exc.close()
        except (URLError, OSError, ValueError, TypeError) as exc:
            meta['error'] = f'{type(exc).__name__}: {exc}'[:500]
        # Do not retry authorization denials, missing resources or invalid content.
        if meta['status'] in (401, 403, 404) or meta['status'] == 200:
            break
        if attempt + 1 < attempts:
            time.sleep(2 ** attempt)
    return meta, None


def build_evidence(live, live_data, source, source_data):
    comparable = bool(live['ok'] and source['ok'] and live_data is not None and source_data is not None)
    return {
        'schema_version': 1,
        'checked_at': now(),
        'live': live,
        'github_source': source,
        'byte_identical': live['sha256'] == source['sha256'] if comparable else None,
        'matches_current_source': canonical(live_data) == canonical(source_data) if comparable else False,
        'live_matches': matching_entries(live_data) if live_data is not None else None,
        'github_source_matches': matching_entries(source_data) if source_data is not None else None,
        'runner': {'kind': 'github_actions' if os.getenv('GITHUB_ACTIONS') == 'true' else 'local',
                   'run_url': (f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/"
                               f"{os.getenv('GITHUB_REPOSITORY')}/actions/runs/{os.getenv('GITHUB_RUN_ID')}"
                               if os.getenv('GITHUB_RUN_ID') else None)},
    }


def main():
    live, live_data = fetch(LIVE)
    source, source_data = fetch(SOURCE)
    evidence = build_evidence(live, live_data, source, source_data)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix('.tmp')
    temporary.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(OUTPUT)
    print(json.dumps({'live_ok': live['ok'], 'live_status': live['status'],
                      'source_ok': source['ok'], 'matches_current_source': evidence['matches_current_source'],
                      'checked_at': evidence['checked_at']}, indent=2))
    # Publish failed observations as evidence too. A failed request is not proof of absence.


if __name__ == '__main__':
    main()
