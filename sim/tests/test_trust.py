import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from terrarium import jobs, machine, trust, worker

LOCK = Path(__file__).resolve().parent.parent / 'uv.lock'


def test_a_job_gets_only_the_environment_it_needs(monkeypatch):
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'sekrit')
    monkeypatch.setenv('PATH', '/usr/bin')
    env = trust.job_env(OMP_NUM_THREADS='2')
    assert env['PATH'] == '/usr/bin' and env['OMP_NUM_THREADS'] == '2' and 'AWS_SECRET_ACCESS_KEY' not in env


def test_packages_only_come_from_the_indexes_and_torch_is_new_enough(tmp_path):
    trust.check_lock(LOCK)
    text = LOCK.read_text()
    git = tmp_path / 'git.lock'
    git.write_text(text + '\n[[package]]\nname = "sneaky"\nversion = "1.0"\nsource = { git = "https://example.com/x.git" }\n')
    with pytest.raises(trust.Refused, match='sneaky'):
        trust.check_lock(git)
    old = tmp_path / 'old.lock'
    old.write_text('[[package]]\nname = "torch"\nversion = "2.5.1"\nsource = { registry = "https://pypi.org/simple" }\n')
    with pytest.raises(trust.Refused, match='2.6'):
        trust.check_lock(old)


def test_a_failure_sent_home_carries_no_home_folder_or_user_name(monkeypatch):
    monkeypatch.setattr(trust.Path, 'home', lambda: Path('/srv/someone'))
    monkeypatch.setattr(trust.getpass, 'getuser', lambda: 'someone')
    said = trust.scrub("FileNotFoundError: '/srv/someone/.terrarium/worker/code/x' (someone's machine)")
    assert 'someone' not in said and "'~/.terrarium/worker/code/x'" in said


def test_times_from_a_lent_machine_go_in_utc():
    assert trust.utc('2026-10-30T20:15:00+1100') == '2026-10-30T09:15:00+0000'
    assert trust.utc('not a time') == 'not a time'


def test_the_signers_are_pinned_on_the_first_run(tmp_path):
    signers = tmp_path / 'allowed_signers'
    signers.write_text(jobs.SIGNERS.read_text())
    home = tmp_path / 'home'
    assert trust.pin_signers(signers, home) is None
    signers.write_text(signers.read_text() + 'someone namespaces="terrarium-job" ssh-ed25519 '
                       'AAAAC3NzaC1lZDI1NTE5AAAAIBESK/Qu45GMmcuUqAByVna1ULVvxrTSz0CFG1EnXPkI\n')
    why = trust.pin_signers(signers, home)
    assert why and 'changed' in why and 'someone SHA256:' in why
    assert trust.pin_signers(signers, home, accept=True) is None and trust.pin_signers(signers, home) is None


def test_linux_idle_comes_from_the_desktop_sessions():
    def reader(sessions: dict):
        def read(cmd):
            if cmd[1] == 'list-sessions':
                return ''.join(f'{sid} 1000 someone seat0 tty2\n' for sid in sessions)
            return sessions[cmd[2]]
        return read
    assert machine.logind_idle(reader({}), now=1000) == float('inf')
    assert machine.logind_idle(reader({'3': 'Type=tty\nIdleHint=no\nIdleSinceHint=0\n'}), now=1000) == float('inf')
    assert machine.logind_idle(reader({'2': 'Type=wayland\nIdleHint=no\nIdleSinceHint=0\n'}), now=1000) == 0
    assert machine.logind_idle(reader({'2': 'Type=x11\nIdleHint=yes\nIdleSinceHint=400000000\n'}), now=1000) == 600


def test_the_status_page_only_takes_orders_from_this_machine(tmp_path):
    class Fake:
        paused = draining = False

        def status(self):
            return {'paused': self.paused}
    fake = Fake()
    server = worker.status_server(fake, 0)  # type: ignore[arg-type]
    port = server.server_address[1]

    def post(host: str, header: bool) -> int:
        req = urllib.request.Request(f'http://127.0.0.1:{port}/pause', data=b'', method='POST',
                                     headers={'Host': host, **({worker.LOCAL: '1'} if header else {})})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
    try:
        assert post(f'127.0.0.1:{port}', False) == 403
        assert post(f'evil.example:{port}', True) == 403
        assert not fake.paused
        assert post(f'127.0.0.1:{port}', True) == 200 and fake.paused
    finally:
        server.shutdown()


def test_a_capped_command_is_unchanged_where_there_is_no_systemd(monkeypatch):
    monkeypatch.setattr(trust.sys, 'platform', 'darwin')
    assert trust.capped(['python', 'x'], 2, 8) == ['python', 'x']
