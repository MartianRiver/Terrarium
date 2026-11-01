# Invite codes for playing on the hosted play server (playserve.py): a friend's name and when the invite runs out,
# signed with a key only River's machine and the play server hold, so the server keeps no list of invites. Every
# invite made with a key dies with it: making a new key on both is how they're all taken back at once.
#   python -m terrarium.invites make Sam [--days 7] [--url https://play.example/]   (key from PLAY_INVITE_KEY)
#   python -m terrarium.invites check CODE
#   python -m terrarium.invites key   (a new random key)

import argparse
import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time

DAYS = 7
MAX_DAYS = 31


class BadInvite(ValueError):
    pass


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


def _sign(key: str, body: str) -> str:
    return _b64(hmac.new(key.encode(), body.encode(), hashlib.sha256).digest()[:16])


def make(key: str, name: str, days: float = DAYS, now: float | None = None) -> str:
    if not 0 < days <= MAX_DAYS:
        raise ValueError(f'an invite lasts more than 0 and at most {MAX_DAYS} days')
    if not name or len(name) > 40:
        raise ValueError('a name of 1 to 40 characters')
    body = _b64(json.dumps({'n': name, 'e': int((now or time.time()) + days * 86400)}, separators=(',', ':')).encode())
    return f'{body}.{_sign(key, body)}'


def check(key: str, code: str, now: float | None = None) -> str:
    """Whose invite this is, or BadInvite saying why it won't do."""
    body, _, sig = code.partition('.')
    if not body or not sig or len(code) > 200 or not hmac.compare_digest(sig, _sign(key, body)):
        raise BadInvite('that invite isn’t one of ours')
    try:
        data = json.loads(_unb64(body))
        name, expires = str(data['n']), float(data['e'])
    except (ValueError, KeyError, TypeError):
        raise BadInvite('that invite isn’t one of ours') from None
    if (now or time.time()) > expires:
        raise BadInvite('that invite has run out: ask River for a new one')
    return name


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    m = sub.add_parser('make')
    m.add_argument('name')
    m.add_argument('--days', type=float, default=DAYS)
    m.add_argument('--url', help='the play page; prints the whole link')
    c = sub.add_parser('check')
    c.add_argument('code')
    sub.add_parser('key')
    args = p.parse_args()
    if args.cmd == 'key':
        print(secrets.token_urlsafe(32))
        return
    key = os.environ.get('PLAY_INVITE_KEY')
    if not key:
        sys.exit('PLAY_INVITE_KEY isn’t set')
    if args.cmd == 'make':
        code = make(key, args.name, args.days)
        print(f'{args.url.rstrip("/")}/?play&invite={code}' if args.url else code)
    else:
        try:
            print(check(key, args.code))
        except BadInvite as e:
            sys.exit(str(e))


if __name__ == '__main__':
    main()
