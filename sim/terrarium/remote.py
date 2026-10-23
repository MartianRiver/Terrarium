# Train on another machine over ssh: ship this commit there as a git bundle, set
# it up with uv (the cuda extra when there's an NVIDIA GPU), train in the
# background so a dropped connection doesn't stop it, and copy runs/ back.
#
#   uv run python -m terrarium.remote start root@HOST -p PORT -- NAME --world configs/solo.toml --workers 12
#   uv run python -m terrarium.remote log root@HOST -p PORT
#   uv run python -m terrarium.remote fetch root@HOST -p PORT
#
# A run copied back can be promoted like a local one, once its commit is on next.

import argparse
import shlex
import subprocess
import tempfile
from pathlib import Path

from .runs import ROOT, dirty, git

# runs on the far side, in the login directory; runs/ is ignored by git, so it outlives each checkout
SETUP = '''set -e
export PATH="$HOME/.local/bin:$PATH"
command -v git >/dev/null && command -v rsync >/dev/null || (apt-get update -qq && apt-get install -y -qq git rsync)
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
[ -d terrarium ] || git clone -q --no-checkout terrarium.bundle terrarium
git -C terrarium fetch -q ../terrarium.bundle
git -C terrarium checkout -q --detach {commit}
cd terrarium/sim
extra=cpu
command -v nvidia-smi >/dev/null && extra=cuda
uv sync -q --locked --extra $extra
# the log lives outside the checkout: inside, it would make the tree dirty and training would refuse to start
nohup uv run --extra $extra python -m terrarium.train {args} > ~/train.log 2>&1 &
echo "training {commit:.7} with the $extra extra; log in ~/train.log"
'''


def ssh(target: str, port: str) -> list[str]:
    return ['ssh', '-p', port, '-o', 'StrictHostKeyChecking=accept-new', target]


def start(target: str, port: str, train_args: list[str]):
    if dirty():
        raise SystemExit('there are uncommitted changes; the far side only gets what is committed')
    commit = git('rev-parse', 'HEAD')
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / 'terrarium.bundle'
        subprocess.run(['git', 'bundle', 'create', '-q', str(bundle), 'HEAD'], check=True, cwd=Path(__file__).parent)
        subprocess.run(['scp', '-q', '-P', port, '-o', 'StrictHostKeyChecking=accept-new', str(bundle),
                        f'{target}:terrarium.bundle'], check=True)
    script = SETUP.format(commit=commit, args=shlex.join(train_args))
    subprocess.run([*ssh(target, port), 'bash -s'], input=script, text=True, check=True)


def log(target: str, port: str, lines: int):
    subprocess.run([*ssh(target, port), f'tail -n {lines} train.log'], check=True)


def fetch(target: str, port: str):
    ROOT.mkdir(exist_ok=True)
    subprocess.run(['rsync', '-az', '-e', shlex.join(ssh(target, port)[:-1]), f'{target}:terrarium/runs/',
                    f'{ROOT}/'], check=True)
    print(f'copied into {ROOT}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start', 'log', 'fetch'])
    parser.add_argument('target', help='user@host, as ssh takes it')
    parser.add_argument('-p', '--port', default='22')
    parser.add_argument('-n', '--lines', type=int, default=20, help='for log: how much of it')
    args, rest = parser.parse_known_args()
    if args.action == 'start':
        if rest[:1] != ['--'] or len(rest) < 2:
            raise SystemExit('start needs the training arguments after --, e.g. -- solo --world configs/solo.toml')
        start(args.target, args.port, rest[1:])
    elif rest:
        parser.error(f'unrecognized arguments: {" ".join(rest)}')
    elif args.action == 'log':
        log(args.target, args.port, args.lines)
    else:
        fetch(args.target, args.port)


if __name__ == '__main__':
    main()
