import hashlib
import json

from terrarium.gallery import Lineage


def make(root, run, parent=None, checkpoints=('00000000010.pt',)):
    path = root / run
    (path / 'checkpoints').mkdir(parents=True)
    for c in checkpoints:
        # a checkpoint holds its run's id, so no two runs' files are the same bytes
        (path / 'checkpoints' / c).write_bytes(f'{run}/{c}'.encode())
    (path / 'run.json').write_text(json.dumps({'id': run, 'started': '2026-10-25T10:00:00+11:00', 'parent': parent}))
    return path


def test_parents_by_meta_by_hash_and_by_bridge(tmp_path):
    first = make(tmp_path, '20261023-100000-first', checkpoints=('00000000005.pt', '00000000010.pt'))
    copied = hashlib.sha256((first / 'checkpoints' / '00000000010.pt').read_bytes()).hexdigest()
    # a copy of first's last checkpoint, from before checkpoints named their run
    make(tmp_path, '20261023-110000-second', {'file': 'parent.pt', 'id': copied})
    # partway through second's run, named in the checkpoint's meta
    make(tmp_path, '20261023-120000-third', {'file': 'parent.pt', 'id': 'x', 'meta': {'run': '20261023-110000-second', 'samples': 10}})
    # made from first without training, so its file matches nothing
    make(tmp_path, '20261023-130000-made', {'file': 'parent.pt', 'id': 'made'})
    lineage = Lineage(tmp_path, {'made': '20261023-100000-first'})
    assert lineage.back('20261023-120000-third', '00000000010.pt') == [
        ('20261023-100000-first', '00000000010.pt'),
        ('20261023-110000-second', '00000000010.pt'),
        ('20261023-120000-third', '00000000010.pt')]
    assert lineage.back('20261023-130000-made', '00000000010.pt')[0] == ('20261023-100000-first', '00000000010.pt')


def test_a_parent_outside_runs_ends_the_line(tmp_path):
    make(tmp_path, '20261023-100000-lone', {'file': 'elsewhere.pt', 'id': 'nothing-here'})
    assert Lineage(tmp_path, {}).back('20261023-100000-lone', '00000000010.pt') == [('20261023-100000-lone', '00000000010.pt')]
