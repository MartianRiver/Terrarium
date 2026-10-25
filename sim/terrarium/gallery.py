# The site's gallery of brains (/brains/): the brain training now, every brain it came from back to the first,
# grouped into the steps site/gallery.toml names, and a few side experiments, each with a replay to watch.
#
#   uv run python -m terrarium.gallery OUT --line 'pbt-t*'
#
# writes OUT/index.json and OUT/<run>-<checkpoint>.jsonl.gz. --line picks the runs of the line being trained
# now (fnmatch on the name after the run's date and time): the best of them that has finished and been scored is
# where the lineage is traced back from, and any of them still training show up as live. [[working]] in gallery.toml
# names something being worked on beside the line: its best few finished runs by one of their evals' numbers. A
# run's parent is the run its parent checkpoint's meta names, or the run with a checkpoint of the same sha256 (a
# copy, made before checkpoints carried their run), or a bridge from gallery.toml for a brain made without training.
import argparse
import fnmatch
import hashlib
import json
import shutil
import time
import tomllib
from pathlib import Path

from . import compute
from .runs import ROOT
from .serve import Runs

STEPS = ROOT.parent / 'site' / 'gallery.toml'
# a run with no new metrics for this long isn't training any more
LIVE = 10 * 60
# how many of the line's newest finished brains to show
NEWEST = 4
SEED = 0


def name(run: Path) -> str:
    # 20261025-031141-pbt-t5-4 -> pbt-t5-4
    return run.name.split('-', 2)[2]


def checkpoint_of(run: Path, samples: int | None) -> str:
    files = sorted(p.name for p in (run / 'checkpoints').glob('*.pt'))
    wanted = f'{samples:011d}.pt' if samples else None
    return wanted if wanted in files else files[-1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Lineage:
    def __init__(self, root: Path, bridges: dict[str, str]):
        self.root = root
        self.runs = {p.name: p for p in root.iterdir() if (p / 'run.json').exists()}
        self.bridges = bridges
        self._hashes: dict[str, tuple[str, str]] | None = None

    def by_hash(self, digest: str) -> tuple[str, str] | None:
        if self._hashes is None:
            self._hashes = {sha256(p): (p.parent.parent.name, p.name) for p in self.root.glob('*/checkpoints/*.pt')}
        return self._hashes.get(digest)

    def parent(self, rec: dict) -> tuple[str, str] | None:
        """The (run, checkpoint) a run started from, if it's in runs/."""
        p = rec.get('parent') or {}
        meta = p.get('meta') or {}
        if meta.get('run') in self.runs:
            return meta['run'], checkpoint_of(self.runs[meta['run']], meta.get('samples'))
        if p.get('id') in self.bridges:
            run = self.bridges[p['id']]
            return run, checkpoint_of(self.runs[run], None)
        return self.by_hash(p['id']) if p.get('id') else None

    def back(self, run: str, checkpoint: str) -> list[tuple[str, str]]:
        """(run, checkpoint) from the first brain to this one."""
        chain = [(run, checkpoint)]
        while (up := self.parent(compute.read_run(self.runs[chain[-1][0]]))) and up not in chain:
            chain.append(up)
        return chain[::-1]


def scores(run: Path, checkpoint: str) -> dict | None:
    """What the run's own evals said about this checkpoint: train's evals.json, or an automated fork's."""
    for f in ('evals.json', 'pbt-evals.json'):
        if not (run / f).exists():
            continue
        data = json.loads((run / f).read_text())
        if data.get('checkpoint') == checkpoint and 'brain' in data:
            return data['brain']
        if checkpoint in data.get('results', {}):
            return data['results'][checkpoint]
    return None


def numbers(s: dict | None) -> dict:
    if not s:
        return {}
    out = {'episodes': s['episodes'], 'alive': round(s['seconds_alive']['mean'], 1),
           'food_per_minute': round(s['food_per_minute']['mean'], 2)}
    if 'stored' in s:
        out['stored'] = round(s['stored']['mean'], 1)
    if 'through_first_night' in s and s.get('deaths', {}).get('colonies'):
        out['through_first_night'] = [s['through_first_night'], s['deaths']['colonies']]
    # worlds with grab: what the vault's doors are for
    if s.get('actions', {}).get('grab_block', {}).get('ticks'):
        out['from_middle'] = round(s['from_middle']['mean'], 2)
        out['blocks_moved'] = round(s['blocks_moved']['mean'], 2)
    return out


def world(rec: dict) -> str:
    c = rec['world']['config']
    if c['colonies']['count'] * c['colonies']['size'] == 1:
        return 'alone'
    parts = [f"{c['colonies']['count']} colonies of {c['colonies']['size']}"]
    if c.get('night', {}).get('cycle'):
        parts.append('nights')
    if c.get('sprint', {}).get('seconds'):
        parts.append('sprint')
    if c.get('grab', {}).get('grip'):
        parts.append('a vault to pull open')
    return ', '.join(parts)


class Gallery:
    def __init__(self, root: Path, out: Path, steps: dict):
        self.root, self.out = root, out
        self.recorder = Runs(root)
        self.lineage = Lineage(root, {b['parent']: b['run'] for b in steps.get('bridge', [])})
        self.steps = steps

    def entry(self, run: str, checkpoint: str, replay: str | None = None) -> dict:
        path = self.lineage.runs[run]
        rec = compute.read_run(path)
        file = f'{run}-{Path(checkpoint).stem}.jsonl.gz'
        if not (self.out / file).exists():
            source = ROOT.parent / replay if replay else self.recorder.replay(run, checkpoint, SEED)
            shutil.copy(source, self.out / file)
        return {'run': run, 'name': name(path), 'checkpoint': checkpoint, 'started': rec['started'],
                'samples': int(Path(checkpoint).stem), 'world': world(rec), 'replay': file,
                # everything behind it, back to the first brain
                'total': sum(int(Path(c).stem) for _, c in self.lineage.back(run, checkpoint)),
                'numbers': numbers(scores(path, checkpoint))}

    def grouped(self, chain: list[tuple[str, str]]) -> list[dict]:
        steps, current = [], None
        for run, checkpoint in chain:
            step = next((s for s in self.steps.get('step', [])
                         if any(fnmatch.fnmatch(name(self.lineage.runs[run]), p) for p in s['runs'])), None)
            if step is not None and step is not current:
                current = step
                steps.append({'title': step['title'], 'text': step['text'], 'brains': []})
            if not steps:
                steps.append({'title': 'Before', 'text': '', 'brains': []})
            steps[-1]['brains'].append(self.entry(run, checkpoint, (step or {}).get('replay')))
        return steps

    def working(self, w: dict) -> dict:
        """The best few finished runs of something being worked on, by the number that says how close it is."""
        found = []
        for p in self.lineage.runs.values():
            note = next((t for pat, t in w['notes'].items() if fnmatch.fnmatch(name(p), pat)), None)
            if note is None or not compute.read_run(p).get('finished'):
                continue
            if s := scores(p, checkpoint_of(p, None)):
                found.append((s[w['score']]['mean'], p.name, note))
        best = sorted(found, reverse=True)[:w['show']]
        return {'title': w['title'], 'text': w['text'],
                'brains': [{**self.entry(run, checkpoint_of(self.lineage.runs[run], None)), 'note': note}
                           for _, run, note in best]}

    def build(self, line: str) -> dict:
        self.out.mkdir(parents=True, exist_ok=True)
        mine = [p for _, p in sorted(self.lineage.runs.items()) if fnmatch.fnmatch(name(p), line)]
        scored = [(s['seconds_alive']['mean'], p.name, checkpoint_of(p, None)) for p in mine
                  if compute.read_run(p).get('finished') and (s := scores(p, checkpoint_of(p, None)))]
        best = max(scored) if scored else None
        now = time.time()
        live = [p for p in mine if not compute.read_run(p).get('finished')
                and (p / 'metrics.jsonl').exists() and now - (p / 'metrics.jsonl').stat().st_mtime < LIVE
                and any((p / 'checkpoints').glob('*.pt'))]
        # runs on rented machines only come back finished, so the newest finished ones stand in for what's training
        done = sorted((p for p in mine if compute.read_run(p).get('finished')),
                      key=lambda p: compute.when(compute.read_run(p)['finished']))
        latest = [p for p in done[::-1][:NEWEST] if p not in live]
        index = {
            'updated': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'line': line,
            'steps': self.grouped(self.lineage.back(best[1], best[2])) if best else [],
            'training': [self.entry(p.name, checkpoint_of(p, None)) for p in live],
            'latest': [{**self.entry(p.name, checkpoint_of(p, None)), 'finished': compute.read_run(p)['finished']}
                       for p in latest],
            'asides': [{'title': a['title'], 'text': a['text'], **self.entry(a['run'], a['checkpoint'], a.get('replay'))}
                       for a in self.steps.get('aside', [])],
            'working': [self.working(w) for w in self.steps.get('working', [])],
        }
        wanted = {'index.json'} | {b['replay'] for s in index['steps'] for b in s['brains']} \
            | {b['replay'] for b in index['training'] + index['latest'] + index['asides']} \
            | {b['replay'] for w in index['working'] for b in w['brains']}
        # a live run's older checkpoints drop off as newer ones come
        for f in self.out.iterdir():
            if f.name not in wanted:
                f.unlink()
        partial = self.out / 'index.json.part'
        partial.write_text(json.dumps(index, indent=1))
        partial.rename(self.out / 'index.json')
        return index


def main():
    parser = argparse.ArgumentParser(description='Build the site gallery of brains from runs/.')
    parser.add_argument('out', type=Path)
    parser.add_argument('--line', required=True, help="fnmatch pattern for the runs of the line training now, e.g. 'pbt-t*'")
    parser.add_argument('--steps', type=Path, default=STEPS)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    index = Gallery(args.root, args.out, tomllib.loads(args.steps.read_text())).build(args.line)
    brains = sum(len(s['brains']) for s in index['steps'])
    print(f"{args.out}: {len(index['steps'])} steps, {brains} brains, {len(index['training'])} training now, "
          f"{len(index['latest'])} newest, {len(index['asides'])} asides, "
          f"{sum(len(w['brains']) for w in index['working'])} being worked on")


if __name__ == '__main__':
    main()
