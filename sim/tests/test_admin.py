import base64
import json
import threading
import time
import urllib.parse
from http.client import HTTPConnection

import pytest

from terrarium import admin, coordinator

ENV = {'GOOGLE_CLIENT_ID': 'client.apps', 'GOOGLE_CLIENT_SECRET': 'secret', 'ADMIN_EMAILS': 'River@Example.com, x@y.z'}


def id_token(**claims) -> str:
    body = {'iss': 'https://accounts.google.com', 'aud': 'client.apps', 'exp': time.time() + 600,
            'email': 'river@example.com', 'email_verified': True} | claims
    part = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b'=').decode()
    return f'{part({"alg": "RS256"})}.{part(body)}.sig'


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A coordinator with sign-in set up; Google's token endpoint answers with whatever `answer` holds."""
    answer = {}

    def exchange(code, verifier, s):
        assert code == 'the-code' and admin.challenge(verifier) == answer['challenge']
        return id_token(**answer['claims'])
    monkeypatch.setattr(admin, 'exchange', exchange)
    root = tmp_path / 'coord'
    httpd = coordinator.serve(root, port=0, signers=None, env=ENV)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield root, httpd.server_address[1], answer
    httpd.shutdown()


def call(port, method, path, cookie='', form=None):
    c = HTTPConnection('127.0.0.1', port)
    body = urllib.parse.urlencode(form).encode() if form is not None else None
    headers = {'Cookie': cookie} | ({'Content-Type': 'application/x-www-form-urlencoded'} if body else {})
    c.request(method, path, body, headers)
    r = c.getresponse()
    return r.status, r.headers, r.read().decode()


def cookie(headers, name, whole=False) -> str:
    found = next(c for c in headers.get_all('Set-Cookie') if c.startswith(name + '='))
    return found if whole else found.split(';')[0]


def sign_in(port, answer, whole=False, **claims) -> tuple[int, str]:
    _, headers, _ = call(port, 'GET', '/api/auth/google/start')
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(headers['Location']).query)
    assert query['scope'] == ['openid email'] and query['code_challenge_method'] == ['S256']
    answer['challenge'], answer['claims'] = query['code_challenge'][0], {'nonce': query['nonce'][0]} | claims
    status, headers, _ = call(port, 'GET', f'/api/auth/google/callback?state={query["state"][0]}&code=the-code',
                              cookie(headers, admin.LOGIN))
    return status, cookie(headers, admin.SESSION, whole) if status == 200 else ''


def form_token(page: str) -> str:
    return page.split('name="form" value="')[1].split('"')[0]


def test_river_signs_in_with_google_and_makes_regenerates_and_revokes_a_token(site):
    root, port, answer = site
    status, set = sign_in(port, answer, whole=True)
    assert status == 200 and all(a in set for a in ('HttpOnly', 'Secure', 'SameSite=Strict', 'Path=/api;'))
    session = set.split(';')[0]
    status, headers, page = call(port, 'GET', '/api/admin', session)
    assert status == 200 and headers['Cache-Control'] == 'no-store' and "frame-ancestors 'none'" in headers['Content-Security-Policy']
    tokens = coordinator.Tokens(root)
    form = form_token(page)
    _, _, page = call(port, 'POST', '/api/admin', session, {'form': form, 'action': 'new', 'name': 'Kelpie', 'role': 'donor'})
    first = page.split('<pre class="token">')[1].split('</pre>')[0]
    assert tokens.who(first) == {'name': 'Kelpie', 'role': 'donor'} and 'Kelpie' in page
    _, _, page = call(port, 'POST', '/api/admin', session, {'form': form, 'action': 'regenerate', 'name': 'Kelpie'})
    second = page.split('<pre class="token">')[1].split('</pre>')[0]
    assert tokens.who(first) is None and tokens.who(second) == {'name': 'Kelpie', 'role': 'donor'}
    call(port, 'POST', '/api/admin', session, {'form': form, 'action': 'revoke', 'name': 'Kelpie'})
    assert tokens.who(second) is None
    _, _, page = call(port, 'POST', '/api/admin', session, {'form': form, 'action': 'out'})
    assert call(port, 'GET', '/api/admin', session)[0] == 401


def test_admin_tokens_are_never_made_or_shown_here(site):
    root, port, answer = site
    tokens = coordinator.Tokens(root)
    river = tokens.add('river-mac', 'admin')
    _, session = sign_in(port, answer)
    form = form_token(call(port, 'GET', '/api/admin', session)[2])
    for f in ({'action': 'new', 'name': 'sneaky', 'role': 'admin'}, {'action': 'regenerate', 'name': 'river-mac'},
              {'action': 'revoke', 'name': 'river-mac'}):
        _, _, page = call(port, 'POST', '/api/admin', session, {'form': form} | f)
        assert 'aren’t handled here' in page and '<pre class="token">' not in page
    assert tokens.who(river) == {'name': 'river-mac', 'role': 'admin'} and len(tokens.load()) == 1


def test_a_form_without_its_token_or_a_session_does_nothing(site):
    root, port, answer = site
    _, session = sign_in(port, answer)
    assert call(port, 'POST', '/api/admin', session, {'form': 'guess', 'action': 'new', 'name': 'x', 'role': 'trusted'})[0] == 403
    assert call(port, 'POST', '/api/admin', '', {'action': 'new', 'name': 'x', 'role': 'trusted'})[0] == 403
    assert coordinator.Tokens(root).load() == {}


@pytest.mark.parametrize('claims', [{'email': 'someone@else.com'}, {'email_verified': False}, {'aud': 'other'},
                                    {'exp': 1}, {'iss': 'https://evil.example'}, {'nonce': 'replayed'}])
def test_only_a_current_verified_listed_account_gets_in(site, claims):
    _, port, answer = site
    assert sign_in(port, answer, **claims)[0] == 403


def test_a_callback_this_browser_did_not_start_is_refused(site):
    _, port, answer = site
    _, headers, _ = call(port, 'GET', '/api/auth/google/start')
    state = urllib.parse.parse_qs(urllib.parse.urlsplit(headers['Location']).query)['state'][0]
    assert call(port, 'GET', f'/api/auth/google/callback?state={state}&code=the-code', f'{admin.LOGIN}=other')[0] == 400
    # and a state is good for one try
    assert call(port, 'GET', f'/api/auth/google/callback?state={state}&code=the-code', f'{admin.LOGIN}={state}')[0] == 400


def test_without_the_settings_the_page_says_so(tmp_path):
    httpd = coordinator.serve(tmp_path, port=0, signers=None, env={})
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        assert call(httpd.server_address[1], 'GET', '/api/admin')[0] == 503
    finally:
        httpd.shutdown()


def test_reliability_counts_each_way_a_job_left_a_machine():
    jobs = [{'history': [[0, 'added'], [1, 'claimed by K'], [2, 'lease ran out on K'], [3, 'claimed by K'],
                         [4, 'given back on K'], [5, 'claimed by P'], [6, 'done by P']]},
            {'history': [[0, 'claimed by K'], [1, 'failed on K']]}]
    assert admin.reliability(jobs) == {'K': {'claimed': 3, 'done': 0, 'lost': 1, 'failed': 1, 'given back': 1},
                                       'P': {'claimed': 1, 'done': 1, 'lost': 0, 'failed': 0, 'given back': 0}}
