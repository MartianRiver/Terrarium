import pytest
import torch

from terrarium.brain import SHAPE, Brain, load, save
from terrarium.widen import widen


def outputs(brain):
    torch.manual_seed(1)
    n = len(brain.schema['ray'])
    me, kinds, rays = torch.randn(64, len(brain.schema['self'])), torch.randint(0, 5, (64, 16)), torch.randn(64, 16, n)
    with torch.no_grad():
        return brain(me, kinds, rays)


@pytest.mark.parametrize('width', [128, 256])
def test_a_widened_brain_acts_as_the_narrow_one(width):
    torch.manual_seed(0)
    old = Brain(**SHAPE)
    for p in old.parameters():
        p.data += torch.randn_like(p) * 0.1
    new = widen(old, width)
    assert new.shape == {'width': width, 'layers': SHAPE['layers'], 'heads': SHAPE['heads'] * width // SHAPE['width']}
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
