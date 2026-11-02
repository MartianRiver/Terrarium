# The pod manager: rents GPU pods on Vast or RunPod when jobs wait in the queue for a rented machine, and gets rid
# of them when they stop being useful. It runs on its own (the Athena box, PLANS "Pods and the queue on Athena"), on
# a bare python: stdlib only, out through the HTTPS proxy, its keys handed in by systemd.
#
#   python3 -m terrarium.pods --state DIR --status FILE [--once] [--dry-run]
#
# Once a minute:
#   - asks the coordinator (with a token of role `pods`) how many jobs wait for a rented machine, and what each of its
#     pods last said;
#   - matches its pods against what each provider says is running, and destroys any pod of its own the ledger
#     doesn't know (an orphan) or that the ledger says is gone;
#   - destroys a pod that never said hello within `start` minutes, went quiet for `quiet` minutes, sat `idle` minutes
#     with nothing to do and nothing waiting, or reached its hours; each one's token is revoked and any job it held
#     goes back to the queue at once;
#   - rents one more pod when jobs wait than pods can take, if the day's spend stays under the cap;
#   - writes status.json for Athena's beacon.
#
# A pod boots itself, no ssh: its start script installs uv, checks out the commit the manager pinned when it rented
# it, and runs the worker with its own token (role rented, gone after `hours`). If the worker ends, or the hours run
# out, the pod stops itself with the provider's own per-pod key. Only pods named terrarium-q-… are ever touched, so
# the Mac's own pod tools and these can't take each other's pods.
#
# Settings are DIR/pods.toml (cap_usd_day, max_pods and the rest of SETTINGS); without it nothing is rented.

import argparse
import base64
import json
import os
import secrets
import sqlite3
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .log import Logger

log = Logger('pods')

SETTINGS = {
    'cap_usd_day': 0.0,       # spend in any 24 h, rentals still running included; 0 rents nothing
    'max_pods': 0,
    'max_dph': 0.40,          # most US$ an hour for one pod
    'providers': ['vast', 'runpod'],
    'vast_gpus': ['RTX 3060', 'RTX 3070', 'RTX 3080', 'RTX 4060 Ti', 'RTX A4000'],
    'runpod_gpus': ['NVIDIA GeForce RTX 3080', 'NVIDIA GeForce RTX 3070', 'NVIDIA RTX A4000'],
    'hours': 6.0,             # a pod's whole life, and its token's
    'start': 15.0,            # minutes to its worker's first hello
    'quiet': 10.0,            # minutes without a word from its worker
    'idle': 5.0,              # minutes with no job and nothing waiting
    'server': 'https://terrarium-jobs.martianriver.com',
    'repo': 'https://github.com/MartianRiver/Terrarium.git',
    'branch': 'next',
}
PREFIX = 'terrarium-q-'
VAST_IMAGE = 'vastai/base-image@sha256:c5b7882c05d74e3de22af79c9698f569eac7725cdadbfc1a23304e5ffc2a1961'
RUNPOD_IMAGE = 'runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04'


def settings(state: Path) -> dict:
    path = state / 'pods.toml'
    got = tomllib.loads(path.read_text()) if path.exists() else {}
    unknown = set(got) - set(SETTINGS)
    if unknown:
        raise ValueError(f'pods.toml: unknown {", ".join(sorted(unknown))}')
    return SETTINGS | got


def secret(name: str, where: Path | None = None) -> str:
    """A key from systemd's LoadCredential, never from the environment or a command line."""
    root = where or Path(os.environ.get('CREDENTIALS_DIRECTORY', '/nonexistent'))
    return (root / name).read_text().strip()


def call(url: str, method: str = 'GET', body=None, headers: dict | None = None):
    req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                                          'User-Agent': 'terrarium-pods'} | (headers or {}))
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b'null')


def boot(server: str, token: str, repo: str, commit: str, hours: float) -> str:
    """The pod's start script. Set -e stops at the first failure, which ends the worker's wait and stops the pod."""
    stop = ('if [ -x /opt/instance-tools/bin/vastai ]; then /opt/instance-tools/bin/vastai stop instance '
            '"$CONTAINER_ID" --api-key "$CONTAINER_API_KEY"; '
            'elif command -v runpodctl >/dev/null; then runpodctl remove pod "$RUNPOD_POD_ID"; fi')
    return f'''#!/bin/bash
exec > /root/boot.log 2>&1
stop() {{ {stop}; }}
(sleep {int(hours * 3600)}; echo "hours up"; stop) &
trap 'echo "worker ended"; stop' EXIT
set -e
umask 077
export DEBIAN_FRONTEND=noninteractive
command -v git >/dev/null || (apt-get update -qq && apt-get install -y -qq git)
command -v uv >/dev/null || (curl -LsSf https://astral.sh/uv/install.sh | sh)
export PATH=$HOME/.local/bin:$PATH
git clone --quiet --filter=blob:none {repo} /root/terrarium
cd /root/terrarium && git checkout --quiet {commit} && cd sim
printf %s '{token}' > /root/token
uv sync --locked --extra cuda
# Vast's instance id, so a run can be matched to its rental (terrarium.compute)
uv run --extra cuda python -m terrarium.worker --server {server} --token-file /root/token --trusted --anytime \
    ${{CONTAINER_ID:+--instance $CONTAINER_ID}}
'''


class Vast:
    name = 'vast'
    base = 'https://console.vast.ai/api/v0'

    def __init__(self, key: str):
        self.key = key

    def api(self, method: str, path: str, body=None):
        return call(('https://console.vast.ai' if path.startswith('/api/') else self.base) + path, method, body,
                    {'Authorization': f'Bearer {self.key}'})

    def live(self) -> dict[str, str]:
        """Our pods the provider has, by id: their label. (v0's list answers 410 now, found 2026-11-02.)"""
        return {str(i['id']): i.get('label') or '' for i in self.api('GET', '/api/v1/instances/')['instances']
                if (i.get('label') or '').startswith(PREFIX)}

    def rent(self, label: str, gpus: list[str], max_dph: float, script: str) -> tuple[str, float] | None:
        q = {'rentable': {'eq': True}, 'verified': {'eq': True}, 'num_gpus': {'eq': 1}, 'gpu_name': {'in': gpus},
             'cuda_max_good': {'gte': 12.6}, 'reliability': {'gte': 0.98}, 'inet_down': {'gte': 300},
             'disk_space': {'gte': 30}, 'dph_total': {'lte': max_dph}, 'type': 'on-demand',
             'order': [['dph_total', 'asc']], 'limit': 20}
        offers = self.api('GET', '/bundles/?' + urllib.parse.urlencode({'q': json.dumps(q)}))['offers']
        for o in offers:
            if (o.get('geolocation') or '').endswith('CN'):
                continue
            try:
                r = self.api('PUT', f"/asks/{o['id']}/", {'client_id': 'me', 'image': VAST_IMAGE, 'disk': 30,
                                                          'label': label, 'runtype': 'ssh_direc ssh_proxy',
                                                          'onstart': script})
            except urllib.error.HTTPError as e:
                log.warn('rent refused', provider='vast', offer=o['id'], status=e.code)
                continue
            if r and r.get('success') and r.get('new_contract'):
                return str(r['new_contract']), float(o['dph_total'])
        return None

    def destroy(self, id: str):
        self.api('DELETE', f'/instances/{id}/')

    def balance(self) -> float | None:
        return self.api('GET', '/users/current/').get('credit')


class RunPod:
    name = 'runpod'

    def __init__(self, key: str):
        self.key = key

    def api(self, query: str, variables=None):
        out = call('https://api.runpod.io/graphql', 'POST', {'query': query, 'variables': variables or {}},
                   {'Authorization': f'Bearer {self.key}'})
        if out.get('errors'):
            raise RuntimeError(out['errors'][0].get('message', 'error'))
        return out['data']

    def live(self) -> dict[str, str]:
        return {p['id']: p['name'] for p in self.api('{ myself { pods { id name } } }')['myself']['pods']
                if p['name'].startswith(PREFIX)}

    def rent(self, label: str, gpus: list[str], max_dph: float, script: str) -> tuple[str, float] | None:
        q = '''mutation($i: PodFindAndDeployOnDemandInput) { podFindAndDeployOnDemand(input: $i) { id costPerHr } }'''
        packed = base64.b64encode(script.encode()).decode()
        for g in gpus:
            i = {'cloudType': 'COMMUNITY', 'gpuCount': 1, 'gpuTypeId': g, 'name': label, 'imageName': RUNPOD_IMAGE,
                 'containerDiskInGb': 30, 'volumeInGb': 0, 'minVcpuCount': 4, 'minMemoryInGb': 16,
                 'dockerArgs': f"bash -c 'echo {packed} | base64 -d > /root/boot.sh && bash /root/boot.sh'"}
            try:
                p = self.api(q, {'i': i})['podFindAndDeployOnDemand']
            except RuntimeError as e:
                log.info('not rented', provider='runpod', gpu=g, why=str(e)[:100])
                continue
            if p and float(p['costPerHr']) <= max_dph:
                return p['id'], float(p['costPerHr'])
            if p:
                self.destroy(p['id'])
        return None

    def destroy(self, id: str):
        self.api('mutation($i: PodTerminateInput!) { podTerminate(input: $i) }', {'i': {'podId': id}})

    def balance(self) -> float | None:
        return self.api('{ myself { clientBalance } }')['myself']['clientBalance']


class Ledger:
    """Every pod rented, kept for good: what it cost and why it went (SQLite, in Athena's nightly backup)."""

    def __init__(self, path: Path):
        self.db = sqlite3.connect(path)
        self.db.execute('create table if not exists pods (name text primary key, provider text, id text, dph real, '
                        'rented real, gone real, why text, commit_sha text, job text)')

    def add(self, name: str, provider: str, id: str, dph: float, now: float, commit: str):
        self.db.execute('insert into pods (name, provider, id, dph, rented, commit_sha) values (?, ?, ?, ?, ?, ?)',
                        (name, provider, id, dph, now, commit))
        self.db.commit()

    def gone(self, name: str, now: float, why: str):
        self.db.execute('update pods set gone = ?, why = ? where name = ? and gone is null', (now, why, name))
        self.db.commit()

    def live(self) -> list[dict]:
        rows = self.db.execute('select name, provider, id, dph, rented from pods where gone is null').fetchall()
        return [dict(zip(('name', 'provider', 'id', 'dph', 'rented'), r)) for r in rows]

    def spent(self, now: float, hours: float = 24) -> float:
        """US$ over the last `hours`, pods still running counted to now."""
        since = now - hours * 3600
        rows = self.db.execute('select dph, rented, coalesce(gone, ?) from pods where coalesce(gone, ?) > ?',
                               (now, now, since)).fetchall()
        return sum(dph * (end - max(start, since)) / 3600 for dph, start, end in rows)


class Manager:
    def __init__(self, state: Path, coordinator, providers: dict, commit, dry: bool = False, now=time.time):
        self.state, self.coordinator, self.providers, self.commit, self.dry, self.now = \
            state, coordinator, providers, commit, dry, now
        self.ledger = Ledger(state / 'ledger.sqlite3')
        self.idle_since: dict[str, float] = {}
        self.reconciled = 0.0

    def tick(self) -> dict:
        cfg, now = settings(self.state), self.now()
        back = self.coordinator('GET', '/api/pods')
        live = {p: prov.live() for p, prov in self.providers.items()}
        self.reconciled = now
        orphans = self.reconcile(live, now)
        for pod in self.ledger.live():
            why = self.why_go(pod, back['pods'].get(pod['name']), back['waiting'], cfg, now)
            if why:
                self.drop(pod, why, now)
        rented = self.maybe_rent(back, cfg, now)
        return {'updated_at_epoch': now, 'last_reconcile_epoch': self.reconciled,
                'spend_24h_usd': round(self.ledger.spent(now), 4), 'spend_cap_usd': cfg['cap_usd_day'],
                'waiting': back['waiting'], 'orphans': orphans, 'rented': rented,
                'pods': [{'provider': p['provider'], 'id': p['id'], 'name': p['name'], 'dph': p['dph'],
                          'job_id': (back['pods'].get(p['name']) or {}).get('job'),
                          'last_heartbeat_epoch': (back['pods'].get(p['name']) or {}).get('seen'),
                          'expected_end_epoch': p['rented'] + cfg['hours'] * 3600} for p in self.ledger.live()]}

    def reconcile(self, live: dict[str, dict[str, str]], now: float) -> int:
        """Pods a provider runs that the ledger doesn't (a crash between renting and writing it down, or one left
        over) are destroyed; ledger pods the provider doesn't list are marked gone."""
        known = {(p['provider'], p['id']) for p in self.ledger.live()}
        orphans = [(prov, id) for prov, ids in live.items() for id in ids if (prov, id) not in known]
        for prov, id in orphans:
            log.warn('orphan pod', provider=prov, id=id, label=live[prov][id])
            if not self.dry:
                self.providers[prov].destroy(id)
        for pod in self.ledger.live():
            if pod['provider'] in live and pod['id'] not in live[pod['provider']]:
                self.ledger.gone(pod['name'], now, 'gone at the provider')
                self.coordinator('POST', f"/api/pods/{pod['name']}/gone", {})
        return len(orphans)

    def why_go(self, pod: dict, said: dict | None, waiting: int, cfg: dict, now: float) -> str | None:
        age = (now - pod['rented']) / 60
        seen = (said or {}).get('seen')
        if age >= cfg['hours'] * 60:
            return 'its hours are up'
        if not seen:
            return f"no hello in {cfg['start']:g} min" if age >= cfg['start'] else None
        if (now - seen) / 60 >= cfg['quiet']:
            return f"quiet for {cfg['quiet']:g} min"
        if (said or {}).get('job') or waiting:
            self.idle_since.pop(pod['name'], None)
            return None
        since = self.idle_since.setdefault(pod['name'], now)
        return f"idle for {cfg['idle']:g} min" if (now - since) / 60 >= cfg['idle'] else None

    def drop(self, pod: dict, why: str, now: float):
        log.info('pod going', name=pod['name'], provider=pod['provider'], id=pod['id'], why=why)
        if self.dry:
            return
        self.providers[pod['provider']].destroy(pod['id'])
        self.coordinator('POST', f"/api/pods/{pod['name']}/gone", {})
        self.ledger.gone(pod['name'], now, why)
        self.idle_since.pop(pod['name'], None)

    def maybe_rent(self, back: dict, cfg: dict, now: float) -> str | None:
        pods = self.ledger.live()
        free = sum(1 for p in pods if not (back['pods'].get(p['name']) or {}).get('job'))
        if back['waiting'] <= free or len(pods) >= cfg['max_pods']:
            return None
        if self.ledger.spent(now) + cfg['max_dph'] * cfg['hours'] > cfg['cap_usd_day']:
            log.info('not renting: over the day\'s cap', spent=round(self.ledger.spent(now), 3), cap=cfg['cap_usd_day'])
            return None
        name = f'pod-{time.strftime("%m%d%H%M", time.gmtime(now))}-{secrets.token_hex(2)}'
        commit = self.commit(cfg)
        if self.dry:
            log.info('would rent', name=name, commit=commit)
            return None
        made = self.coordinator('POST', f'/api/pods/{name}', {'hours': cfg['hours']})
        script = boot(cfg['server'], made['token'], cfg['repo'], commit, cfg['hours'])
        for p in cfg['providers']:
            got = self.providers[p].rent(PREFIX + name, cfg[f'{p}_gpus'], cfg['max_dph'], script)
            if got:
                id, dph = got
                self.ledger.add(name, p, id, dph, now, commit)
                log.info('rented', name=name, provider=p, id=id, dph=dph, commit=commit)
                return name
        self.coordinator('POST', f'/api/pods/{name}/gone', {})
        log.warn('nothing rentable', providers=cfg['providers'])
        return None


def tip(cfg: dict) -> str:
    """The branch's newest commit, read from GitHub (api.github.com is on Athena's allow list)."""
    owner_repo = cfg['repo'].removeprefix('https://github.com/').removesuffix('.git')
    return call(f"https://api.github.com/repos/{owner_repo}/commits/{cfg['branch']}")['sha']


def write_status(path: Path, status: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + '.part')
    part.write_text(json.dumps(status, indent=1) + '\n')
    part.replace(path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--status', type=Path, required=True)
    p.add_argument('--credentials', type=Path, help="default: systemd's $CREDENTIALS_DIRECTORY")
    p.add_argument('--once', action='store_true')
    p.add_argument('--dry-run', action='store_true', help='decide and log, but rent, destroy and revoke nothing')
    p.add_argument('--every', type=float, default=60, help='seconds between rounds')
    args = p.parse_args()
    args.state.mkdir(parents=True, exist_ok=True)
    cfg = settings(args.state)
    token = secret('coordinator_token', args.credentials)

    def coordinator(method: str, path: str, body=None):
        return call(cfg['server'] + path, method, body, {'Authorization': f'Bearer {token}'})

    providers = {'vast': Vast(secret('vast_api_key', args.credentials)),
                 'runpod': RunPod(secret('runpod_api_key', args.credentials))}
    manager = Manager(args.state, coordinator, providers, tip, args.dry_run)
    while True:
        try:
            status = manager.tick()
            for name, prov in providers.items():
                try:
                    status.setdefault('balances', {})[name] = prov.balance()
                except Exception as e:
                    log.warn('no balance', provider=name, error=repr(e))
            write_status(args.status, status)
        except Exception as e:
            log.error('round failed', error=repr(e), exc=True)
        if args.once:
            break
        time.sleep(args.every)


if __name__ == '__main__':
    main()
