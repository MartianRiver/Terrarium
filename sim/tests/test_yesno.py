import numpy as np
import torch

from terrarium import schema
from terrarium.brain import NO_ODDS, SHAPE, Brain, load, save
from terrarium.train import train

from test_ppo import short
from test_widen import outputs


def coins(brain) -> torch.Tensor:
    return torch.tensor(np.isin(brain.schema['actions'], schema.YES_NO))


def test_a_brain_turned_to_coins_says_yes_about_as_often():
    torch.manual_seed(0)
    brain = Brain(**SHAPE)
    for p in brain.parameters():
        p.data += torch.randn_like(p) * 0.1
    mean, _ = outputs(brain)
    spread = brain.log_std.detach().exp()
    before = torch.distributions.Normal(0, 1).cdf(mean / spread)[:, coins(brain)].numpy()
    steer = mean[:, ~coins(brain)]
    brain.to_bernoulli()
    mean, _ = outputs(brain)
    after = torch.sigmoid(mean)[:, coins(brain)].numpy()
    assert np.abs(before - after).max() < 0.02
    assert torch.equal(mean[:, ~coins(brain)], steer)


def test_coins_are_tossed_as_plus_or_minus_one_and_scored_as_coins():
    brain = Brain(**SHAPE, yes_no='bernoulli')
    mean = torch.zeros(1000, len(brain.schema['actions']))
    dist = brain.dist(mean)
    action = dist.sample()
    tossed = action[:, coins(brain)]
    assert set(tossed.unique().tolist()) == {-1.0, 1.0} and 0.4 < (tossed > 0).float().mean() < 0.6
    assert torch.allclose(dist.log_prob(action)[:, coins(brain)], torch.tensor(np.log(0.5), dtype=torch.float32))
    assert torch.allclose(dist.entropy()[0, coins(brain)], torch.tensor(np.log(2), dtype=torch.float32))
    # a fresh coin says yes about as rarely as a fresh Gaussian yes/no does
    assert Brain(**SHAPE, yes_no='bernoulli').policy.bias[coins(brain)].eq(NO_ODDS).all()


def test_coins_are_kept_through_a_save_and_old_brains_stay_gaussian(tmp_path):
    brain = Brain(**SHAPE)
    save(brain, tmp_path / 'old.pt')
    assert load(tmp_path / 'old.pt')[0].yes_no == 'gaussian'
    brain.to_bernoulli()
    save(brain, tmp_path / 'coins.pt')
    assert load(tmp_path / 'coins.pt')[0].yes_no == 'bernoulli'


def test_a_brain_with_coins_trains(tmp_path):
    world, trainer = short(tmp_path)
    parent = tmp_path / 'coins.pt'
    brain = Brain(**SHAPE)
    brain.to_bernoulli()
    save(brain, parent)
    run = train('coins', world, trainer, parent=parent, scratch=True, root=tmp_path / 'runs', device='cpu')
    trained, _ = load(run.dir / 'checkpoints' / '00000000256.pt')
    assert trained.yes_no == 'bernoulli' and not torch.equal(trained.policy.weight, brain.policy.weight)
