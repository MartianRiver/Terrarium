# The code a job runs: a commit, shipped as a git bundle of HEAD, plus an
# overlay when the tree is dirty: a tar.gz of every changed or untracked file
# under sim/ and a list of the ones deleted. A worker clones the commit and
# lays the overlay on top, so the tree it trains in is dirty in the same way and
# the run comes out as scratch, with its own diff.patch, never promotable.
#
# Donors never take a bundle or an overlay: they fetch the commit from the
# public repo themselves and only run it if it's on main or next (worker.py).

import gzip
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from .log import Logger
from .store import member

log = Logger('snapshot')

REPO = Path(__file__).resolve().parent.parent.parent
PUBLIC = ('origin/main', 'origin/next')
MANIFEST = '.overlay.json'


def git(*args, cwd: Path = REPO, check: bool = True) -> str:
    return subprocess.run(['git', *args], capture_output=True, text=True, cwd=cwd, check=check).stdout.strip()


def commit(repo: Path = REPO) -> str:
    return git('rev-parse', 'HEAD', cwd=repo)


def bundle(repo: Path = REPO) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'code.bundle'
        git('bundle', 'create', '-q', str(path), 'HEAD', cwd=repo)
        return path.read_bytes()


def overlay(repo: Path = REPO, under: str = 'sim') -> bytes | None:
    """sim/'s uncommitted state as a tar.gz, or None for a clean tree. The manifest inside lists deletions."""
    # not git(): its strip() would eat the first entry's leading space, which is part of its status code
    status = subprocess.run(['git', 'status', '--porcelain', '-z', '--untracked-files=all', '--', under],
                            capture_output=True, text=True, cwd=repo, check=True).stdout
    if not status:
        return None
    changed, deleted = [], []
    entries = status.split('\0')
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if not entry:
            continue
        code, path = entry[:2], entry[3:]
        if code[0] == 'R':
            # renames carry the old name as the next entry
            deleted.append(entries[i])
            i += 1
        (deleted if 'D' in code else changed).append(path)
    buf = io.BytesIO()
    # no timestamps anywhere, so the same tree is the same blob and workers reuse its checkout
    with gzip.GzipFile(fileobj=buf, mode='wb', mtime=0) as gz, \
            tarfile.open(fileobj=gz, mode='w', format=tarfile.PAX_FORMAT) as tar:
        for path in sorted(changed):
            info = tar.gettarinfo(str(repo / path), arcname=path)
            info.mtime, info.uid, info.gid, info.uname, info.gname = 0, 0, 0, '', ''
            with open(repo / path, 'rb') as f:
                tar.addfile(info, f)
        manifest = json.dumps({'deleted': sorted(deleted)}).encode()
        info = tarfile.TarInfo(MANIFEST)
        info.size = len(manifest)
        tar.addfile(info, io.BytesIO(manifest))
    return buf.getvalue()


def public(commit: str, repo: Path) -> bool:
    for ref in PUBLIC:
        if subprocess.run(['git', 'merge-base', '--is-ancestor', commit, ref], cwd=repo,
                          capture_output=True).returncode == 0:
            return True
    return False


def apply(tree: Path, data: bytes):
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as tar:
        manifest = json.loads(member(tar, MANIFEST))
        # the data filter refuses absolute paths, .. and links out of the tree
        tar.extractall(tree, members=[m for m in tar.getmembers() if m.name != MANIFEST], filter='data')
    for path in manifest['deleted']:
        target = (tree / path).resolve()
        if tree.resolve() in target.parents and target.is_file():
            target.unlink()


def from_bundle(dest: Path, data: bytes, commit: str, extra: bytes | None = None):
    """A checkout of commit from a bundle, with the overlay on top."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'code.bundle'
        path.write_bytes(data)
        git('clone', '-q', '--no-checkout', str(path), str(dest), cwd=Path(tmp))
    git('checkout', '-q', '--detach', commit, cwd=dest)
    if extra:
        apply(dest, extra)


def from_public(dest: Path, mirror: Path, url: str, commit: str):
    """A checkout of a commit that's on the public repo's main or next, fetched from there."""
    if not mirror.exists():
        git('clone', '-q', '--mirror', url, str(mirror), cwd=mirror.parent)
    else:
        git('remote', 'update', '--prune', cwd=mirror)
    # a mirror's branches are refs/heads/*; name them the way public() looks for them
    for branch in ('main', 'next'):
        if git('rev-parse', '--verify', '-q', f'refs/heads/{branch}', cwd=mirror, check=False):
            git('update-ref', f'refs/remotes/origin/{branch}', f'refs/heads/{branch}', cwd=mirror)
    if not public(commit, mirror):
        raise PermissionError(f'{commit[:12]} is not on the public main or next')
    git('clone', '-q', '--no-checkout', '--shared', str(mirror), str(dest), cwd=mirror.parent)
    git('checkout', '-q', '--detach', commit, cwd=dest)


def remove(tree: Path):
    # git makes its pack files read-only, which Windows won't delete
    def unlock(func, path, _):
        os.chmod(path, 0o700)
        func(path)
    shutil.rmtree(tree, onexc=unlock)
