# What a worker strips out and checks so a lent machine has to trust as little as it can (docs/compute.md, "What
# you're still trusting"): a job gets a short list of the worker's environment, never the rest; a commit is refused if
# its packages could come from anywhere but the package indexes, or its torch can be made to run code by a brain file;
# a failure's log tail goes without the machine's home folder and user name, and a run's times go in UTC; on Linux a
# job is held to its share of the cores; and the keys that may sign jobs are pinned the first time the worker runs.

import base64
import datetime
import getpass
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from .log import Logger

log = Logger('worker')

# all a job gets of the worker's environment: enough to find its tools, its home and its temp folder, and to reach
# the package indexes through a proxy. Anything else (tokens and keys people keep in their environment) stays out
KEEP_ENV = ('PATH', 'HOME', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA', 'SYSTEMROOT', 'SYSTEMDRIVE', 'WINDIR', 'COMSPEC',
            'PATHEXT', 'TEMP', 'TMP', 'TMPDIR', 'LANG', 'LC_ALL', 'NUMBER_OF_PROCESSORS', 'PROCESSOR_ARCHITECTURE',
            'CUDA_VISIBLE_DEVICES', 'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'no_proxy',
            'SSL_CERT_FILE', 'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS', 'HOMEDRIVE', 'HOMEPATH', 'PROGRAMDATA',
            'CUDA_PATH', 'UV_CACHE_DIR', 'UV_PYTHON_INSTALL_DIR')
# where a job's packages may come from; anything else in its uv.lock (a git repo, a URL, a path) is refused
INDEXES = ('https://pypi.org/simple', 'https://download.pytorch.org/whl/')
# torch.load(weights_only=True) could run code before 2.6 (CVE-2025-32434)
TORCH_AT_LEAST = (2, 6)
# checkouts of past commits kept (each has its own packages, CUDA torch included: a few GB)
KEEP_CODE = 3


class Refused(Exception):
    pass


def job_env(**extra: str) -> dict[str, str]:
    return {k: v for k in KEEP_ENV if (v := os.environ.get(k))} | extra


def capped(cmd: list[str], cores: float, of: int) -> list[str]:
    """On Linux, the command in a systemd scope that holds it to `cores` of the machine's `of`, a hard cap like
    Windows' job object rather than the thread counts and low priority that are all macOS gets. Unchanged if there's
    no user systemd to ask (a container, an old distro)."""
    if sys.platform != 'linux' or cores >= of or not shutil.which('systemd-run'):
        return cmd
    if subprocess.run(['systemd-run', '--user', '--scope', '--quiet', 'true'], capture_output=True).returncode:
        return cmd
    # the scope's systemd-run becomes the command itself, so its pid is still the job's
    return ['systemd-run', '--user', '--scope', '--quiet', '-p', f'CPUQuota={max(1, round(cores * 100))}%', *cmd]


def check_lock(lock: Path):
    """Refuse a commit whose packages could come from anywhere but the package indexes, or whose torch can be made
    to run code by a brain file."""
    for pkg in tomllib.loads(lock.read_text()).get('package', []):
        source = pkg.get('source', {})
        if 'registry' in source:
            if not source['registry'].startswith(INDEXES):
                raise Refused(f'{pkg["name"]} comes from {source["registry"]}, not a package index this worker allows')
        elif not (source.get('editable') == '.' or source.get('virtual') == '.'):
            raise Refused(f'{pkg["name"]} comes from {source}, not a package index')
        if pkg['name'] == 'torch':
            version = tuple(int(x) for x in re.findall(r'\d+', pkg['version'])[:2])
            if version < TORCH_AT_LEAST:
                raise Refused(f'torch {pkg["version"]} can run code from a brain file; this worker needs 2.6 or later')


def scrub(text: str) -> str:
    """A failure's log tail, without this machine's home folder or user name, before it's sent."""
    home = str(Path.home())
    for variant in {home, home.replace('\\', '/'), home.replace('/', '\\')}:
        text = text.replace(variant, '~')
    user = getpass.getuser()
    return re.sub(rf'\b{re.escape(user)}\b', 'user', text) if len(user) > 2 else text


def utc(stamp: str) -> str:
    """A run.json time in UTC, so a run sent from a lent machine doesn't say which time zone it's in."""
    try:
        return datetime.datetime.strptime(stamp, '%Y-%m-%dT%H:%M:%S%z').astimezone(datetime.timezone.utc).strftime(
            '%Y-%m-%dT%H:%M:%S%z')
    except (TypeError, ValueError):
        return stamp


def fingerprints(signers: str) -> list[str]:
    """Each key in an allowed_signers file as `principal SHA256:…`, the way ssh-keygen -l shows them."""
    out = []
    for line in signers.splitlines():
        parts = line.split()
        if not parts or parts[0].startswith('#'):
            continue
        blob = next((b for a, b in zip(parts, parts[1:]) if a.startswith(('ssh-', 'ecdsa-', 'sk-'))), None)
        if blob:
            digest = base64.b64encode(hashlib.sha256(base64.b64decode(blob)).digest()).decode().rstrip('=')
            out.append(f'{parts[0]} SHA256:{digest}')
    return out


def pin_signers(signers: Path, home: Path, accept: bool = False) -> str | None:
    """The keys this worker trusts, fixed the first time it runs. A pull that changes allowed_signers would change who
    can send this machine jobs, so the worker stops and says so until it's started with --trust-new-signers. None
    when it's fine, else why it won't start."""
    pinned, now = home / 'signers.pinned', signers.read_text()
    if pinned.exists() and pinned.read_text() != now and not accept:
        return ('allowed_signers changed since this worker first trusted it.\n'
                f'  was: {", ".join(fingerprints(pinned.read_text())) or "(none)"}\n'
                f'  now: {", ".join(fingerprints(now)) or "(none)"}\n'
                'Check the change in the repo history (git log -p sim/allowed_signers), then start the worker once with '
                '--trust-new-signers.')
    if not pinned.exists() or pinned.read_text() != now:
        home.mkdir(parents=True, exist_ok=True)
        pinned.write_text(now)
        log.info('trusting these signers', keys=fingerprints(now))
    return None
