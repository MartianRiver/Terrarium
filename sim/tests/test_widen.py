import pytest
import torch

from terrarium.brain import SHAPE, Brain, load, save
from terrarium.widen import widen


def outputs(brain):
    torch.manual_seed(1)
    n = len(brain.schema['ray'])
    me, kinds, rays = torch.randn(64, len(brain.schema['self'])), torch.randint(0, 5, (64, 16)), torch.randn(64, 16, n)
    with torch.no_grad():
        return brain(me, kinds, rays)[:2]


@pytest.mark.parametrize('width', [128, 256])
def test_a_widened_brain_acts_as_the_narrow_one(width):
    torch.manual_seed(0)
    old = Brain(**SHAPE)
    for p in old.parameters():
        p.data += torch.randn_like(p) * 0.1
    new = widen(old, width)
    assert new.shape == {'width': width, 'layers': SHAPE['layers'], 'heads': SHAPE['heads'] * width // SHAPE['width'], 'memory': 0}
    for a, b in zip(outputs(old), outputs(new)):
        assert torch.allclose(a, b, atol=1e-5)


def test_noise_parts_the_copies_but_keeps_close():
    torch.manual_seed(0)
    old = Brain(**SHAPE)
    new = widen(old, 128, noise=0.01)
    w = new.state_dict()['encoder.layers.0.linear1.weight']
    assert not torch.equal(w[:128], w[128:])
    mean_old, _ = outputs(old)
    mean_new, _ = outputs(new)
    assert (mean_old - mean_new).abs().max() < 0.05


def test_width_must_be_a_multiple(tmp_path):
    with pytest.raises(ValueError):
        widen(Brain(**SHAPE), 96)
    new = widen(Brain(**SHAPE), 128)
    save(new, tmp_path / 'wide.pt')
    loaded, _ = load(tmp_path / 'wide.pt')
    assert loaded.shape['width'] == 128


def with_notes():
    torch.manual_seed(0)
    old = Brain(**SHAPE).with_memory(16, recall=1.0)
    for p in old.parameters():
        p.data += torch.randn_like(p) * 0.1
    return old


def run(brain, steps=6):
    # the same observations each call, notes carried from one step to the next
    torch.manual_seed(1)
    n = len(brain.schema['ray'])
    me, kinds, rays = torch.randn(steps, 8, len(brain.schema['self'])), torch.randint(0, 5, (steps, 8, 16)), torch.randn(steps, 8, 16, n)
    notes, means, values = brain.blank(8), [], []
    with torch.no_grad():
        for i in range(steps):
            mean, value, notes = brain(me[i], kinds[i], rays[i], notes)
            means.append(mean)
            values.append(value)
    return torch.stack(means), torch.stack(values), notes


@pytest.mark.parametrize('width', [128, 256])
def test_a_widened_brain_with_memory_acts_and_remembers_the_same(width):
    old = with_notes()
    new = widen(old, width)
    assert new.shape['memory'] == 16
    for a, b in zip(run(old), run(new)):
        assert torch.allclose(a, b, atol=1e-4)
    # the notes differ from blank, or the check above proves little
    assert run(old)[2].abs().max() > 0.1


def test_noise_leaves_the_notes_reader_alone_and_keeps_close():
    old = with_notes()
    new = widen(old, 128, noise=0.01)
    assert torch.equal(new.gru.weight_hh, old.gru.weight_hh)
    means_old, _, notes_old = run(old)
    means_new, _, notes_new = run(new)
    assert not torch.equal(means_old, means_new)
    assert (means_old - means_new).abs().max() < 0.1
    assert (notes_old - notes_new).abs().max() < 0.1


def test_memory_size_survives_a_save(tmp_path):
    save(widen(with_notes(), 128), tmp_path / 'wide.pt')
    loaded, _ = load(tmp_path / 'wide.pt')
    assert loaded.shape['width'] == 128 and loaded.memory == 16
