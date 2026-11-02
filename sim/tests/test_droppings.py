from dataclasses import replace

import numpy as np

from terrarium import evals, load
from terrarium.config import DEFAULT
from terrarium.forage import observe
from terrarium.replay import frame
from terrarium.schema import ACTIONS, SELF
from terrarium.vision import DUNG, look
from terrarium.world import World

COLONY = load(DEFAULT.parent / 'colony.toml')
DUNG_ON = replace(COLONY.dung, every=2, after=1.0, lasts=60.0, slots=8, radius=0.08, near=0.5, sick=0.01, away=1.0)
CARRY = ACTIONS.index('carry')


def world_of(**dung):
    cfg = replace(COLONY, colonies=replace(COLONY.colonies, count=1, size=1, room=0), block=(),
                  dung=replace(DUNG_ON, **dung))
    world = World(cfg)
    world.heading[:] = -np.pi / 2
    world.food_regrow[:] = 10**9
    world.flower_due[:] = 10**9
    world.clock[:] = 30.0
    return world


def step(world, carry=-1.0, thrust=0.0):
    act = np.full((1, 1, len(ACTIONS)), -1.0)
    act[..., 0], act[..., 1] = thrust, 0.0
    act[0, 0, CARRY] = carry
    world.step(act)


def lay(world, k, at):
    world.dung.pos[0, k] = at
    world.dung.left[0, k] = 10**6


def test_meals_become_a_dropping_behind_it_later_that_makes_it_sick():
    world, d = world_of(), DUNG_ON
    world.dung.step(np.array([[2]]))
    assert world.dung.digest[0, 0] > 0 and not world.dung.left.any()
    for _ in range(round(d.after * world.cfg.tick_hz)):
        step(world)
    assert world.dung.lying()[0].sum() == 1 and world.dung.made[0, 0] == 1
    assert world.dung.dirt()[0, 0] == 1
    assert observe(world, np.zeros((1, 1, 2))).me[0, SELF.index('dirty')] > 0
    a = world.energy[0, 0]
    step(world)
    assert a - world.energy[0, 0] > (world.cfg.energy.drain + d.sick * 0.9) * world.cfg.dt


def test_a_dropping_is_seen_carried_off_and_counted_as_moved_away():
    world = world_of()
    me = world.pos[0, 0].copy()
    lay(world, 0, me + (0.0, -(world.cfg.creature.radius + DUNG_ON.radius + 0.1)))
    assert (look(world).kind == DUNG).any()
    step(world, carry=1.0)
    assert world.dung.load[0, 0] == 0 and world.dung.dirt()[0, 0] == 0
    assert not (look(world).kind == DUNG).any()
    assert frame(world, 0)['creatures'][0]['dung'] == 1 and frame(world, 0)['dung'] == []
    for _ in range(30):
        step(world, thrust=1.0)
    step(world, carry=1.0)
    assert world.dung.load[0, 0] == -1 and world.dung.tidied[0, 0] > 1.0
    assert len(frame(world, 0)['dung']) == 1


def test_a_pile_is_only_as_bad_as_one_dropping():
    world = world_of(pile=0.3)
    me = world.pos[0, 0]
    for k, dx in enumerate((0.0, 0.1, 0.2)):
        lay(world, k, me + (dx, 0.0))
    assert np.isclose(world.dung.dirt()[0, 0], 1.0)
    spread = world_of()
    for k, dx in enumerate((0.0, 0.1, 0.2)):
        lay(spread, k, spread.pos[0, 0] + (dx, 0.0))
    assert np.isclose(spread.dung.dirt()[0, 0], 3.0)


def test_the_tidy_nursery_pays_for_one_taken_out_and_puts_a_new_one_at_home():
    world = world_of(every=0, start=3, midden=1.0, points=1.0)
    nest, r, dung = world.nests[0], world.cfg.colonies.nest_radius, world.dung
    assert dung.lying()[0].sum() == 3
    assert (np.hypot(*(dung.pos[0][dung.lying()[0]] - nest).T) <= r).all()
    k = int(np.flatnonzero(dung.lying()[0])[0])
    dung.pick(0, 0, k)
    dung.put(0, 0, nest + (0.0, -(r + 0.5)))
    assert dung.points(world.alive)[0, 0] == 0
    dung.pick(0, 0, k)
    dung.put(0, 0, nest + (0.0, -(r + 1.5)))
    # from inside the midden line to past it: paid, gone, and another in the nest
    assert dung.points(world.alive)[0, 0] == 1.0 and dung.taken[0, 0] == 1
    assert dung.lying()[0].sum() == 3
    # one already out doesn't pay again for going further
    out = int(np.flatnonzero(dung.left[0] == 0)[0])
    lay(world, out, nest + (0.0, -(r + 2.0)))
    dung.pick(0, 0, out)
    dung.put(0, 0, nest + (0.0, -(r + 3.0)))
    assert dung.points(world.alive)[0, 0] == 0


def test_a_midden_spot_keeps_what_lands_on_it_on_a_heap_that_cant_be_picked_up_or_paid_twice():
    world = world_of(every=0, start=2, slots=6, midden=3.0, points=1.0, spot=0.5, heap=2, wander=0.0)
    nest, r, dung = world.nests[0], world.cfg.colonies.nest_radius, world.dung
    spot = dung.midden_at[0]
    assert np.allclose(spot, nest + (r + 3.0, 0.0))
    # two on the heap from the start, two loose in the nest
    assert dung.heaped[0].sum() == 2 and dung.loose()[0].sum() == 2
    assert (np.hypot(*(dung.pos[0][dung.heaped[0]] - spot).T) < 0.5).all()
    k = int(np.flatnonzero(dung.loose()[0])[0])
    # past where the line would be, but off the spot: nothing
    dung.pick(0, 0, k)
    dung.put(0, 0, nest + (0.0, -(r + 3.0)))
    assert dung.points(world.alive)[0, 0] == 0
    dung.pick(0, 0, k)
    dung.put(0, 0, spot + (0.2, 0.1))
    assert dung.points(world.alive)[0, 0] == 1.0 and dung.heaped[0, k]
    # it stays on the heap, a new one turns up at home, and the heap is out of reach
    assert dung.lying()[0, k] and dung.loose()[0].sum() == 2
    world.pos[0, 0] = spot + (0.3, 0.0)
    world.load[:] = -1
    assert not (dung.in_reach()[0, 0] and dung.nearest(0, 0)[0] in np.flatnonzero(dung.heaped[0]))
    # slots full: the heap's oldest makes room for the next one at home
    for _ in range(3):
        k = int(np.flatnonzero(dung.loose()[0])[0])
        dung.pick(0, 0, k)
        dung.put(0, 0, spot)
    assert dung.loose()[0].sum() == 2 and dung.heaped[0].sum() == 4 and dung.taken[0, 0] == 4


def test_trips_time_the_first_one_out_and_the_ones_after():
    world = world_of(every=0, start=1, slots=6, midden=3.0, points=1.0, spot=0.5, heap=1, wander=0.0)
    dung, spot = world.dung, world.dung.midden_at[0]
    for at in (100, 160, 180):
        world.age[0] = at
        k = int(np.flatnonzero(dung.loose()[0])[0])
        dung.pick(0, 0, k)
        dung.put(0, 0, spot)
    assert dung.first_trip[0, 0] == 100 and dung.later_trips[0, 0] == 80 and dung.taken[0, 0] == 3
    trips = evals.trips(dung.taken, dung.first_trip, dung.later_trips, 20)
    assert trips == {'first_trip': 5.0, 'later_trip': 2.0}


def test_a_wandering_midden_moves_each_episode_and_stays_in_the_arena():
    world = world_of(every=0, start=1, slots=4, midden=3.0, points=1.0, spot=0.5, heap=1, wander=180.0)
    bearings = []
    for _ in range(8):
        world.dung.reset(np.arange(1))
        x, y = world.dung.midden_at[0] - world.nests[0]
        assert np.hypot(x, y) <= world.cfg.colonies.nest_radius + 3.0 + 1e-9
        assert (np.abs(world.dung.midden_at[0]) <= world.cfg.arena.size / 2 - 0.5).all()
        bearings.append(np.arctan2(y, x))
    assert np.ptp(bearings) > 2.0


def test_off_by_default_and_a_brain_sees_it_last():
    world = World(COLONY, 2, seed=0)
    assert world.dung is None
    obs = observe(world, np.zeros((*world.alive.shape, 2)))
    assert obs.me.shape[-1] == len(SELF) and SELF[-2:] == ('dirty', 'dung_load')
    assert (obs.me[:, -2:] == 0).all()
