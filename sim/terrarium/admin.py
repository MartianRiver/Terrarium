# River's page on the coordinator, at /api/admin: a token for each machine's handle (made, regenerated,
# revoked) and what each machine has done, signed in with Google. Only the addresses in ADMIN_EMAILS get in.
# Nothing about the Google account is kept: a session is a random id held in memory (gone on a restart),
# and the address is only compared, never stored or logged.
#
# The settings come from the environment (an EnvironmentFile on Atlas): GOOGLE_CLIENT_ID,
# GOOGLE_CLIENT_SECRET, ADMIN_EMAILS (comma-separated) and PUBLIC_URL. Without them the page says so.
#
# The ID token comes straight from Google's token endpoint over TLS, in exchange for the code and the
# client secret and the PKCE verifier, so its signature needn't be checked here (OpenID Connect Core
# 3.1.3.7); its issuer, audience, expiry, nonce and verified address are. An ID token from a browser is
# never accepted.

import base64
import hashlib
import html
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.cookies import SimpleCookie

from . import board
from .log import Logger
from .store import sha256

log = Logger('admin')

AUTH = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN = 'https://oauth2.googleapis.com/token'
ISSUERS = ('https://accounts.google.com', 'accounts.google.com')
SESSION_HOURS = 12
LOGIN_MINUTES = 10
FORM_LIMIT = 4096
# sign-ins started and not finished, at most: each is a few bytes, but /start needs no token
PENDING = 1000
ROLES = ('donor', 'trusted', 'rented')
SESSION, LOGIN = 'tj_admin', 'tj_login'
HEADERS = {'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
           'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
                                      "frame-ancestors 'none'; base-uri 'none'"}


@dataclass(frozen=True)
class Settings:
    client_id: str
    secret: str
    admins: frozenset[str]
    url: str

    @property
    def callback(self) -> str:
        return f'{self.url}/api/auth/google/callback'


def settings(env=os.environ) -> Settings | None:
    id, secret = env.get('GOOGLE_CLIENT_ID', ''), env.get('GOOGLE_CLIENT_SECRET', '')
    admins = frozenset(a.strip().lower() for a in env.get('ADMIN_EMAILS', '').split(',') if a.strip())
    if not (id and secret and admins):
        return None
    return Settings(id, secret, admins, env.get('PUBLIC_URL', 'https://terrarium-jobs.martianriver.com').rstrip('/'))


def challenge(verifier: str) -> str:
    """PKCE (S256): a code seen in a log is useless without the verifier, which never leaves the coordinator."""
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()


def exchange(code: str, verifier: str, s: Settings) -> str:
    """The code for Google's ID token."""
    body = urllib.parse.urlencode({'code': code, 'client_id': s.client_id, 'client_secret': s.secret,
                                   'redirect_uri': s.callback, 'grant_type': 'authorization_code',
                                   'code_verifier': verifier}).encode()
    req = urllib.request.Request(TOKEN, body, {'User-Agent': 'terrarium-jobs',
                                               'Content-Type': 'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())['id_token']


def claims(id_token: str, s: Settings, nonce: str, now: float) -> str | None:
    """The verified address, if the token is for us, current, ours and verified; else None."""
    try:
        payload = id_token.split('.')[1]
        c = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return None
    ok = (c.get('iss') in ISSUERS and c.get('aud') == s.client_id and isinstance(c.get('exp'), (int, float))
          and c['exp'] > now and c.get('nonce') == nonce and c.get('email_verified') is True)
    return str(c.get('email', '')).lower() if ok else None


def reliability(jobs: list[dict]) -> dict[str, dict[str, int]]:
    """Per machine, from the jobs' history: lost leases (it went quiet) count against it most, failures next;
    a hand-back is what the rules ask of a lent machine, so it's only counted."""
    out: dict[str, dict[str, int]] = {}
    for job in jobs:
        for _, what in job['history']:
            for kind, prefix in (('claimed', 'claimed by '), ('done', 'done by '), ('lost', 'lease ran out on '),
                                 ('failed', 'failed on '), ('given back', 'given back on ')):
                if what.startswith(prefix):
                    counts = out.setdefault(what[len(prefix):], dict.fromkeys(
                        ('claimed', 'done', 'lost', 'failed', 'given back'), 0))
                    counts[kind] += 1
    return out


class Desk:
    """Sessions and sign-ins in memory, and the page."""

    def __init__(self, queue, env=os.environ):
        self.queue, self.settings = queue, settings(env)
        self.sessions: dict[str, dict] = {}
        self.logins: dict[str, dict] = {}
        self.lock = threading.Lock()

    def handle(self, req, method: str, parts: list[str]):
        if self.settings is None:
            return self.page(req, '<p>Sign-in isn’t set up on this coordinator (no Google client or admin list).</p>', 503)
        match method, parts:
            case 'GET', ['api', 'auth', 'google', 'start']:
                return self.start(req)
            case 'GET', ['api', 'auth', 'google', 'callback']:
                return self.callback(req)
            case 'GET', ['api', 'admin']:
                return self.show(req, self.session(req))
            case 'POST', ['api', 'admin']:
                return self.act(req)
        self.page(req, '<p>Nothing here.</p>', 404)

    # signing in

    def start(self, req):
        s = self.settings
        assert s is not None
        state, nonce, verifier = (secrets.token_urlsafe(n) for n in (24, 24, 48))
        now = time.time()
        with self.lock:
            self.logins = {k: v for k, v in self.logins.items() if v['expires'] > now}
            full = len(self.logins) >= PENDING
            if not full:
                self.logins[state] = {'nonce': nonce, 'verifier': verifier, 'expires': now + LOGIN_MINUTES * 60}
        if full:
            return self.page(req, '<p>Too many sign-ins at once. Try again in a few minutes.</p>', 429)
        query = urllib.parse.urlencode({'client_id': s.client_id, 'redirect_uri': s.callback, 'response_type': 'code',
                                        'scope': 'openid email', 'state': state, 'nonce': nonce,
                                        'code_challenge': challenge(verifier), 'code_challenge_method': 'S256',
                                        'prompt': 'select_account'})
        # Lax: it has to come back with Google's redirect to the callback
        self.send(req, 302, b'', 'text/plain', {'Location': f'{AUTH}?{query}'},
                  [f'{LOGIN}={state}; Path=/api/auth; HttpOnly; Secure; SameSite=Lax; Max-Age={LOGIN_MINUTES * 60}'])

    def callback(self, req):
        s = self.settings
        assert s is not None
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(req.path).query)
        state, code = query.get('state', [''])[0], query.get('code', [''])[0]
        with self.lock:
            login = self.logins.pop(state, None)
        cookie = cookies(req).get(LOGIN)
        # the state has to be one this browser was given, or anyone could sign River into their session
        if not login or login['expires'] < time.time() or not code or cookie is None or cookie.value != state:
            return self.page(req, '<p>That sign-in didn’t start here or took too long. <a href="/api/auth/google/start">Try again</a>.</p>', 400)
        try:
            email = claims(exchange(code, login['verifier'], s), s, login['nonce'], time.time())
        except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
            log.warn('google sign-in failed', error=repr(e)[:200])
            return self.page(req, '<p>Google didn’t answer as expected. <a href="/api/auth/google/start">Try again</a>.</p>', 502)
        if email is None or email not in s.admins:
            log.warn('sign-in refused')
            return self.page(req, '<p>That account can’t sign in here.</p>', 403)
        id = secrets.token_urlsafe(32)
        with self.lock:
            now = time.time()
            self.sessions = {k: v for k, v in self.sessions.items() if v['expires'] > now}
            self.sessions[sha256(id.encode())] = {'expires': now + SESSION_HOURS * 3600, 'form': secrets.token_urlsafe(24)}
        log.info('admin signed in')
        # a page, not a redirect: a Strict cookie isn't sent on a redirect chain that began at Google
        self.send(req, 200, page('Signed in', '<meta http-equiv="refresh" content="0; url=/api/admin">'
                                 '<p><a href="/api/admin">Carry on</a></p>'), 'text/html; charset=utf-8', {},
                  [f'{SESSION}={id}; Path=/api; HttpOnly; Secure; SameSite=Strict; Max-Age={SESSION_HOURS * 3600}',
                   f'{LOGIN}=; Path=/api/auth; HttpOnly; Secure; SameSite=Lax; Max-Age=0'])

    def session(self, req) -> dict | None:
        c = cookies(req).get(SESSION)
        if c is None:
            return None
        with self.lock:
            found = self.sessions.get(sha256(c.value.encode()))
        return found if found and found['expires'] > time.time() else None

    # the page

    def act(self, req):
        found = self.session(req)
        length = req.headers.get('Content-Length', '')
        if not length.isdigit() or int(length) > FORM_LIMIT:
            return self.page(req, '<p>That form was too big.</p>', 413)
        form = {k: v[0] for k, v in urllib.parse.parse_qs(req.rfile.read(int(length)).decode()).items()}
        if found is None or not secrets.compare_digest(form.get('form', ''), found['form']):
            return self.page(req, '<p>Signed out, or that form is stale. <a href="/api/admin">Back</a>.</p>', 403)
        action, name, tokens = form.get('action'), form.get('name', '').strip(), self.queue.tokens
        # admin tokens are made on River's own machine, never shown in a browser
        held = next((t['role'] for t in tokens.load().values() if t['name'] == name), None)
        if held == 'admin' or (action == 'new' and form.get('role') not in ROLES):
            return self.show(req, found, 'Admin tokens aren’t handled here.')
        try:
            if action == 'new':
                return self.issued(req, found, name, tokens.add(name, form.get('role', 'donor')))
            if action == 'regenerate':
                if held is None:
                    raise ValueError(f'{name} has no token')
                role = held
                tokens.revoke(name)
                return self.issued(req, found, name, tokens.add(name, role))
            if action == 'revoke':
                tokens.revoke(name)
                log.info('token revoked', name=name)
                return self.show(req, found, f'{name}’s token no longer works.')
            if action == 'out':
                with self.lock:
                    self.sessions = {k: v for k, v in self.sessions.items() if v is not found}
                return self.page(req, '<p>Signed out.</p>', 200, [f'{SESSION}=; Path=/api; HttpOnly; Secure; SameSite=Strict; Max-Age=0'])
        except ValueError as e:
            return self.show(req, found, str(e))
        self.show(req, found, 'Nothing done.')

    def issued(self, req, found: dict, name: str, token: str):
        log.info('token made', name=name)
        self.show(req, found, f'The token for {name}. It isn’t shown again, so copy it now:', token)

    def show(self, req, found: dict | None, note: str = '', token: str = ''):
        if found is None:
            return self.page(req, '<p><a class="button" href="/api/auth/google/start">Sign in with Google</a></p>', 401)
        q = self.queue
        jobs = q.store.all()
        done, steady = board.work(jobs), reliability(jobs)
        tokens = {t['name']: t['role'] for t in q.tokens.load().values()}
        with q.lock:
            workers = json.loads(json.dumps(q.workers))
        form = f'<input type="hidden" name="form" value="{found["form"]}">'
        rows = []
        for name in sorted(set(tokens) | set(workers), key=str.lower):
            w, n = workers.get(name, {}), steady.get(name, {})
            info, d = w.get('info') or {}, done.get(name, {})
            gpus, cpu, memory = parts(info.get('specs') or {})
            seen = ago(time.time() - w['seen']) if w.get('seen') else 'never'
            role = tokens.get(name)
            buttons = 'on the Mac' if role == 'admin' else (f'<form method="post">{form}<input type="hidden" name="name" value="{esc(name)}">'
                       '<button name="action" value="regenerate">New token</button>'
                       '<button name="action" value="revoke">Revoke</button></form>') if role else 'revoked'
            rows.append(f'<tr><td>{esc(name)}</td><td>{esc(role or w.get("role", ""))}</td>'
                        f'<td>{esc(info.get("state", "–"))} <small>{esc(info.get("reason", ""))}</small></td>'
                        f'<td>{esc(info.get("version", "–"))}</td>'
                        f'<td>{seen}</td><td>{esc(gpus)}</td><td>{esc(cpu)}</td><td>{esc(memory)}</td><td>{n.get("done", 0)}</td><td>{n.get("lost", 0)}</td>'
                        f'<td>{n.get("failed", 0)}</td><td>{n.get("given back", 0)}</td>'
                        f'<td>{d.get("samples", 0) / 1e6:.1f}M</td><td>{buttons}</td></tr>')
        roles = ''.join(f'<option>{r}</option>' for r in ROLES)
        body = ((f'<p class="note">{esc(note)}</p>' if note else '')
                + (f'<pre class="token">{esc(token)}</pre>' if token else '')
                + '<h2>Machines</h2><table><tr><th>Handle</th><th>Role</th><th>Now</th><th>Version</th><th>Last seen</th><th>GPU</th><th>CPU</th><th>Memory</th>'
                  '<th>Done</th><th>Lost</th><th>Failed</th><th>Given back</th><th>Samples</th><th></th></tr>'
                + ''.join(rows) + '</table>'
                + f'<h2>New token</h2><form method="post">{form}<input name="name" placeholder="handle" required '
                  f'pattern="[A-Za-z0-9_.\\-]{{1,80}}"> <select name="role">{roles}</select> '
                  '<button name="action" value="new">Make it</button></form>'
                + f'<form method="post" class="out">{form}<button name="action" value="out">Sign out</button></form>')
        self.page(req, body, 200)

    def page(self, req, body: str, status: int, cookies: list[str] | None = None):
        self.send(req, status, page('Terrarium jobs', body), 'text/html; charset=utf-8', {}, cookies or [])

    def send(self, req, status: int, body: bytes, kind: str, headers: dict, cookies: list[str]):
        req.send_response(status)
        for k, v in {'Content-Type': kind, 'Content-Length': str(len(body)), **HEADERS, **headers}.items():
            req.send_header(k, v)
        for c in cookies:
            req.send_header('Set-Cookie', c)
        req.end_headers()
        req.wfile.write(body)


def ago(seconds: float) -> str:
    # the server's clock is UTC, so no times of day
    m = round(seconds / 60)
    return f'{m} min ago' if m < 120 else f'{m / 60:.0f} h ago' if m < 48 * 60 else f'{m / 1440:.0f} days ago'


def parts(specs: dict) -> tuple[str, str, str]:
    gpus = ', '.join(f"{g['name']} ({g['memory_gb']} GB)" if g.get('memory_gb') else g['name']
                     for g in specs.get('gpus') or [] if g.get('name')) or '–'
    cpu = ' · '.join(str(x) for x in (specs.get('cpu'), specs.get('cores') and f"{specs['cores']} threads", specs.get('os')) if x) or '–'
    memory = f"{specs['memory_gb']} GB" if specs.get('memory_gb') else '–'
    return gpus, cpu, memory


def esc(s) -> str:
    return html.escape(str(s))


def cookies(req) -> SimpleCookie:
    c = SimpleCookie()
    try:
        c.load(req.headers.get('Cookie', ''))
    except Exception:
        pass
    return c


def page(title: str, body: str) -> bytes:
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>{esc(title)}</title>
<style>
body {{ font: 15px/1.5 system-ui, sans-serif; margin: 16px; color: #2c3a33; background: #fbf6ee; }}
table {{ border-collapse: collapse; font-variant-numeric: tabular-nums; display: block; overflow-x: auto; }}
th, td {{ padding: 4px 10px 4px 0; border-bottom: 1px solid #e6dccb; text-align: left; white-space: nowrap; }}
small {{ color: #6b7a70; }}
.token {{ padding: 12px; background: #fff; border: 2px solid #c46d40; border-radius: 8px; user-select: all; }}
.note {{ font-weight: 600; }}
.out {{ margin-top: 2em; }}
button, .button, input, select {{ font: inherit; margin: 2px; }}
@media (prefers-color-scheme: dark) {{ body {{ color: #e9e6f2; background: #1b1f36; }} .token {{ background: #232845; }} }}
</style></head><body><h1>Terrarium jobs</h1>
{body}
</body></html>
'''.encode()
