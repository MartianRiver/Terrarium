from dataclasses import replace

import numpy as np
import pytest
import torch

from terrarium import load, schema, vision
from terrarium.brain import SHAPE, Brain, brain_id, save, tensors
from terrarium.brain import load as load_brain
from terrarium.config import DEFAULT, load_train
from terrarium.evals import brain_policy, run
from terrarium.forage import Forage, carried_worth
from terrarium.schema import SchemaError

SOLO = load(DEFAULT.parent / 'solo.toml')
TRAIN = load_train()
REWARD = TRAIN.reward


def observation(seed=0, kinds=len(schema.KINDS), batch=32, rays=16):
    g = torch.Generator().manual_seed(seed)
    return (torch.randn(batch, len(schema.SELF), generator=g), torch.randint(0, kinds, (batch, rays), generator=g),
            torch.randn(batch, rays, len(schema.RAY), generator=g))


def test_kinds_are_in_visions_order():
    assert [getattr(vision, k.upper()) for k in schema.KINDS] == list(range(len(schema.KINDS)))


def test_schema_takes_its_own_and_older():
    schema.check(schema.current())
    old = schema.current() | {'self': schema.current()['self'][:2], 'kinds': ['nothing', 'wall']}
    schema.check(old)


def test_schema_refuses_a_renamed_input():
    renamed = schema.current()
    renamed['ray'] = ['distance', 'angle', 'cos']
    with pytest.raises(SchemaError, match=r"ray\[1\] is 'angle' in the brain .* but 'sin' here"):
        schema.check(renamed)


def test_schema_refuses_a_newer_brain():
    newer = schema.current()
    newer['actions'] = newer['actions'] + ['signal']
    with pytest.raises(SchemaError, match="has actions this code doesn't .*: signal"):
        schema.check(newer)


def test_checkpoint_round_trip(tmp_path):
    torch.manual_seed(0)
    brain = Brain(**SHAPE)
    path = tmp_path / 'b.pt'
    first = save(brain, path, run='test', step=3)
    again, meta = load_brain(path)
    assert meta == {'run': 'test', 'step': 3} and first == brain_id(path)
    obs = observation()
    for a, b in zip(brain(*obs), again(*obs)):
        assert torch.equal(a, b)


def test_a_brain_from_shorter_lists_acts_the_same(tmp_path):
    """Grown lists load as zero weights: the old brain's actions and values come out unchanged."""
    torch.manual_seed(1)
    now = schema.current()
    old = now | {'self': now['self'][:3], 'ray': now['ray'][:2], 'kinds': now['kinds'][:3], 'actions': now['actions'][:1]}
    brain = Brain(**SHAPE, lists=old)
    save(brain, tmp_path / 'old.pt')
    grown, _ = load_brain(tmp_path / 'old.pt')

    me, kinds, rays = observation(kinds=3)
    mean, value, _ = brain(me[:, :3], kinds, rays[..., :2])
    mean2, value2, _ = grown(me, kinds, rays)
    assert torch.allclose(value, value2, atol=1e-6)
    assert torch.allclose(mean, mean2[:, :1], atol=1e-6)
    assert (mean2[:, 1] == 0).all()


def test_a_new_yes_no_action_is_tried_now_and_then(tmp_path):
    """Grown unload and eat lean no: yes on about 5% of samples, and never when acting on the mean."""
    torch.manual_seed(2)
    now = schema.current()
    brain = Brain(**SHAPE, lists=now | {'actions': now['actions'][:2]})
    save(brain, tmp_path / 'old.pt')
    grown, _ = load_brain(tmp_path / 'old.pt')
    obs = Forage(SOLO, TRAIN, 64, seed=0).observe()
    yes = np.concatenate([grown.act(obs)[0] for _ in range(50)]) > 0
    for name in schema.YES_NO:
        i = schema.ACTIONS.index(name)
        assert 0.03 < yes[:, i].mean() < 0.07
        assert (grown.act(obs, sample=False)[0][:, i] < 0).all()


def test_not_a_brain_is_refused(tmp_path):
    torch.save({'weights': {}}, tmp_path / 'x.pt')
    with pytest.raises(SchemaError, match="isn't a Terrarium brain"):
        load_brain(tmp_path / 'x.pt')


def test_forage_observes_every_creature():
    env = Forage(SOLO, TRAIN, 3, seed=0)
    obs = env.observe()
    rays = SOLO.vision.rays
    assert obs.me.shape == (3, len(schema.SELF)) and obs.kinds.shape == (3, rays)
    assert obs.rays.shape == (3, rays, len(schema.RAY)) and obs.me.dtype == obs.rays.dtype == np.float32
    assert (obs.rays[..., 0] <= 1).all() and (obs.me[:, 0] == SOLO.energy.start).all()
    mean, value, _ = Brain(**SHAPE)(*tensors(obs, 'cpu'))
    assert mean.shape == (3, len(schema.ACTIONS)) and value.shape == (3,)


def test_forage_rewards_eating_and_dying_and_starts_over():
    env = Forage(SOLO, TRAIN, 2, seed=0)
    w = env.world
    w.energy[0, 0] = 0.5
    w.food_pos[0, 0] = w.pos[0, 0]
    w.energy[1, 0] = 0.0001
    w.food_regrow[1] = 1
    _, reward, done, ended = env.step(np.zeros((2, 2)))
    assert reward[0] == pytest.approx(REWARD.food) and reward[1] == pytest.approx(REWARD.death)
    assert list(done) == [False, True] and list(ended) == [False, True]
    # arena 1 has already started over
    assert w.alive[1, 0] and w.age[1] == 0 and w.energy[1, 0] == SOLO.energy.start


COLONY = replace(load(), block=(), colonies=replace(load().colonies, count=2, size=2))


def test_a_creature_dying_ends_only_its_own_stream():
    env = Forage(COLONY, TRAIN, 1, seed=0)
    env.world.energy[0, 1] = 0.0001
    _, _, done, ended = env.step(np.zeros((4, 2)))
    assert list(done) == [False, True, False, False] and not ended[0]
    assert list(env.active) == [True, False, True, True]


def test_reward_is_shared_with_the_colony():
    env = Forage(COLONY, TRAIN, 1, seed=0)
    w = env.world
    w.energy[:] = 0.5
    w.food_pos[0, 0] = w.pos[0, 0]
    _, reward, *_ = env.step(np.zeros((4, 2)))
    share = REWARD.colony * REWARD.food / 2
    assert reward == pytest.approx([(1 - REWARD.colony) * REWARD.food + share, share, 0, 0])


def test_food_pays_when_eaten_not_when_picked_up():
    env = Forage(SOLO, replace(TRAIN, reward=replace(REWARD, home=0.0)), 1, seed=0)
    w = env.world
    w.energy[:] = 0.9
    w.food_pos[0, 0] = w.pos[0, 0]
    _, reward, *_ = env.step(np.zeros((1, 4)))
    assert w.crop[0, 0] == 1 and reward[0] == 0, 'carried, not eaten'
    _, reward, *_ = env.step(np.array([[0.0, 0.0, -1.0, 1.0]]))
    assert w.crop[0, 0] == 1 and reward[0] == 0, 'too full to eat it'
    w.energy[:] = 0.5
    _, reward, *_ = env.step(np.array([[0.0, 0.0, -1.0, 1.0]]))
    assert w.crop[0, 0] == 0 and reward[0] == pytest.approx(REWARD.food)


def carrying(at):
    """A solo Terrikin with a full crop and no food about, standing this far east of its nest."""
    env = Forage(replace(SOLO, block=()), TRAIN, 1, seed=0)
    w = env.world
    w.food_regrow[:] = 1
    w.crop[:] = SOLO.crop.capacity
    w.physics.bodies[0][0].position = tuple(w.nests[0] + (at, 0.0))
    w.physics.read()
    return env


def test_carrying_home_pays_on_the_way_and_walking_off_takes_it_back():
    # holding worth costs (1 - gamma) of it a tick, so what matters is home against away, not the sign
    last = {}
    for heading in (np.pi, 0.0):
        env = carrying(6.0)
        w = env.world
        w.heading[:] = heading
        for _ in range(9):
            env.step(np.array([[1.0, 0.0]]))
        worth = carried_worth(w, REWARD)[0, 0]
        _, reward, *_ = env.step(np.array([[1.0, 0.0]]))
        assert reward[0] == pytest.approx(TRAIN.ppo.gamma * carried_worth(w, REWARD)[0, 0] - worth)
        last[heading] = reward[0]
    assert last[np.pi] > 0.005 + last[0.0]
    env = carrying(6.0)
    env.world.crop[:] = 0
    _, reward, *_ = env.step(np.array([[1.0, 0.0]]))
    assert reward[0] == 0, 'nothing carried, nothing paid'


def test_a_choice_held_for_ticks_is_those_ticks_played_one_by_one():
    # with no discount the shaping adds up the same either way, so the rewards must too
    train = replace(TRAIN, ppo=replace(TRAIN.ppo, gamma=1.0))
    held = Forage(SOLO, replace(train, ppo=replace(train.ppo, repeat=4)), 2, seed=3)
    ticked = Forage(SOLO, train, 2, seed=3)
    action = np.tile([[1.0, 0.3, -1.0, -1.0]], (2, 1))
    for _ in range(25):
        _, reward, done, _ = held.step(action)
        total = sum(ticked.step(action)[1] for _ in range(4))
        assert reward == pytest.approx(total)
        assert (held.world.pos == ticked.world.pos).all() and (held.world.fed == ticked.world.fed).all()
    with pytest.raises(ValueError, match='whole number'):
        Forage(SOLO, replace(train, ppo=replace(train.ppo, repeat=7)), 1, seed=0)


def test_unloading_at_home_pays_the_store_less_what_carrying_it_there_paid():
    env = carrying(0.0)
    worth = carried_worth(env.world, REWARD)[0, 0]
    assert worth == pytest.approx(REWARD.home * SOLO.crop.capacity)
    _, reward, *_ = env.step(np.array([[0.0, 0.0, 1.0, -1.0]]))
    assert reward[0] == pytest.approx(REWARD.stored * SOLO.crop.capacity - worth)


def test_dying_with_a_full_crop_loses_what_it_was_worth():
    env = carrying(0.0)
    env.world.energy[:] = 0.0001
    _, reward, done, _ = env.step(np.zeros((1, 2)))
    assert done[0] and reward[0] == pytest.approx(REWARD.death - REWARD.home * SOLO.crop.capacity)


def test_carrying_is_seen():
    env = Forage(SOLO, TRAIN, 1, seed=0)
    env.world.crop[:] = 1
    assert env.observe().me[0, schema.SELF.index('carrying')] == pytest.approx(1 / SOLO.crop.capacity)


def test_it_knows_when_its_home():
    env = carrying(0.0)
    at_home = schema.SELF.index('at_home')
    assert env.observe().me[0, at_home] == 1
    env = carrying(SOLO.colonies.nest_radius + 1.0)
    assert env.observe().me[0, at_home] == 0


def test_an_action_can_start_over(tmp_path):
    brain = Brain(**SHAPE)
    eat = schema.ACTIONS.index('eat')
    with torch.no_grad():
        brain.policy.weight[eat] = 1.0
        brain.policy.bias[eat] = 3.0
    obs = Forage(SOLO, TRAIN, 2, seed=0).observe()
    before, _ = brain.act(obs, sample=False)
    brain.restart(('eat',))
    after, _ = brain.act(obs, sample=False)
    assert np.allclose(after[:, eat], -1.0) and np.allclose(after[:, :eat], before[:, :eat])
    with pytest.raises(ValueError):
        brain.restart(('fly',))


def test_it_knows_whether_its_colony_has_jelly():
    env = Forage(load(DEFAULT), TRAIN, 1, seed=0)
    store = schema.SELF.index('store')
    assert (env.observe().me[:, store] == 0).all()
    env.world.store[0, 1] = env.world.cfg.colonies.size
    seen = env.observe().me[:, store].reshape(env.world.colony.shape)
    mine = env.world.colony == 1
    assert seen[mine] == pytest.approx(np.tanh(1.0)) and (seen[~mine] == 0).all()


def test_forward_and_side_speed():
    env = Forage(replace(SOLO, block=()), TRAIN, 1, seed=0)
    env.world.heading[:] = np.pi / 2
    obs = env.observe()
    for _ in range(20):
        obs, *_ = env.step(np.array([[1.0, 0.0]]))
    assert obs.me[0, 1] == pytest.approx(1.0, abs=0.02) and abs(obs.me[0, 2]) < 0.02
    assert list(obs.me[0, 3:5]) == [1.0, 0.0]


def test_home_sense():
    env = Forage(replace(SOLO, block=()), TRAIN, 1, seed=0)
    w = env.world
    w.physics.bodies[0][0].position = tuple(w.nests[0] + (3.0, 0))
    w.physics.read()
    home = slice(schema.SELF.index('home_distance'), schema.SELF.index('home_cos') + 1)
    w.heading[:] = np.pi
    assert list(env.observe().me[0, home]) == pytest.approx([3.0 / SOLO.vision.range, 0, 1], abs=1e-6)
    # facing up, home is a quarter turn to its left
    w.heading[:] = np.pi / 2
    assert list(env.observe().me[0, home]) == pytest.approx([3.0 / SOLO.vision.range, 1, 0], abs=1e-6)


def test_evals_take_a_brain(tmp_path):
    torch.manual_seed(2)
    save(Brain(**SHAPE), tmp_path / 'b.pt')
    short = replace(SOLO, episode=replace(SOLO.episode, seconds=5.0))
    r = run(short, brain_policy(tmp_path / 'b.pt'), 2)
    assert 0 < r['seconds_alive']['mean'] <= 5.0


def test_the_coin_bonus_keeps_a_coin_from_settling_on_never():
    from terrarium import ppo
    torch.manual_seed(0)
    brain = Brain(32, 1, 2, yes_no='bernoulli')
    eat = schema.ACTIONS.index('eat')
    with torch.no_grad():
        brain.policy.bias[eat] = -3.0
    me, kinds, rays = torch.zeros(64, len(schema.SELF)), torch.zeros(64, 4, dtype=torch.long), torch.zeros(64, 4, len(schema.RAY))
    mean, value, _ = brain(me, kinds, rays)
    dist = brain.dist(mean)
    coins = brain.coins()
    assert torch.allclose(dist.coin_entropy(), torch.where(coins, dist.coin.entropy(), 0.0).sum(-1))
    actions = dist.sample().detach()
    old = dist.log_prob(actions).sum(-1).detach()
    zero = torch.zeros(64)
    opt = torch.optim.Adam(brain.parameters(), lr=1e-2)
    for _ in range(20):
        mean, value, _ = brain(me, kinds, rays)
        ppo.step(brain, opt, replace(TRAIN.ppo, coins=0.1), {k: [] for k in ('policy_loss', 'value_loss', 'entropy', 'kl', 'clipped')},
                 mean, value.squeeze(-1), actions, old, zero, zero)
    assert brain.policy.bias[eat] > -2.9
    # aimed at one coin, the bonus leaves the others alone
    sprint = schema.ACTIONS.index('sprint')
    assert torch.allclose(dist.coin_entropy(brain.named(('sprint',))), dist.coin.entropy()[..., sprint])


def test_sense_skips_the_last_layers_other_tokens_and_says_the_same():
    torch.manual_seed(3)
    for width, layers, heads in ((64, 2, 4), (128, 2, 8), (32, 1, 4)):
        b = Brain(width, layers, heads).eval()
        n, s = 5, b.schema
        me, rays = torch.randn(n, len(s['self'])), torch.randn(n, 16, len(s['ray']))
        kinds = torch.randint(0, len(s['kinds']), (n, 16))
        tokens = torch.cat([b.me(me)[:, None], b.kind(kinds) + b.ray(rays)], 1)
        with torch.no_grad():
            whole = b.norm(b.encoder(tokens)[:, 0])
            assert torch.allclose(b.sense(me, kinds, rays), whole, atol=1e-5)
