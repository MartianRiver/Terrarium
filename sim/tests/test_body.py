from dataclasses import replace
from pathlib import Path
import platform

import numpy as np
import pytest

from terrarium import load, replay
from terrarium.budget import body as costs, budget, show
from terrarium.config import DEFAULT, Config, ConfigError, build
from terrarium.forage import observe
from terrarium.schema import SELF
from terrarium import body
from terrarium.body import CHILLED, STARVED, THIRST
from terrarium.world import World
from golden_body import GAMES, record

CONFIGS = DEFAULT.parent
SOLO = load(CONFIGS / 'solo.toml')
NIGHT = load(CONFIGS / 'night.toml')
WATER = load(CONFIGS / 'nursery-water.toml')
COLONY = load(CONFIGS / 'colony.toml')
BLOCKS = load(CONFIGS / 'blocks.toml')
DT = SOLO.dt


def lone(cfg=SOLO, food=0, **sections):
    """One nim, no food unless asked, a section or two changed: `energy=dict(move=0.0)`."""
    cfg = replace(cfg, food=replace(cfg.food, count=food), colonies=replace(cfg.colonies, count=1, size=1, room=0),
                  crop=replace(cfg.crop, capacity=0, start=0))
    return replace(cfg, **{k: replace(getattr(cfg, k), **v) for k, v in sections.items()})


def push(world, thrust=0.0, ticks=1):
    x = np.zeros((world.arenas, len(world.colony), 2))
    x[..., 0] = thrust
    for _ in range(ticks):
        world.step(x)


def put(world, at):
    world.physics.bodies[0][0].position = tuple(at)
    world.physics.read()


def at_night(world, seconds=70.0):
    """Arena 0 `seconds` into its day: past a 60 s day, it's night."""
    world.age[:] = round(seconds * world.cfg.tick_hz)


# off means the same world

BODY_KEYS = {'energy': ('rest', 'sleep', 'still', 'work'), 'colonies': ('nest_area',), 'crop': ('mass',), 'tired': ('warm', 'dark')}


def without_body(cfg: Config) -> dict:
    """The world as a lab file from before would have it: none of the new sections or keys."""
    data = cfg.to_dict()
    del data['fat']
    for section, keys in BODY_KEYS.items():
        for key in keys:
            del data[section][key]
    return data


@pytest.mark.parametrize('cfg', [SOLO, NIGHT, COLONY, WATER], ids=['solo', 'night', 'colony', 'water'])
def test_a_world_file_without_the_new_keys_loads_with_them_off(cfg):
    old = build(Config, without_body(cfg))
    assert old == cfg
    assert not World(old, 1, 0).fat.any()


GOLDEN = Path(__file__).parent / 'data' / 'body_off.npz'


def test_the_games_the_golden_trace_holds_cover_what_the_body_touches():
    want = np.load(GOLDEN)
    games = {k.split('/')[0] for k in want.files}
    assert games == {g[0] for g in GAMES}
    last = lambda g, k: want[f'{g}/{k}'][-1].sum()
    assert want['running out/alive'][-1].sum() < want['running out/alive'][0].sum()
    assert want['night and dawn/chill'].max() > 0.5 and want['night and dawn/alive'][-1].sum() < want['night and dawn/alive'][0].sum()
    assert last('feeding', 'fed') > 0 and last('hatching', 'hatched') > 0 and last('hatching', 'jelly') > 0
    assert last('grass', 'grazed') > 0 and last('flowers and crop', 'drunk') > 0 and last('water', 'jumps') > 0
    assert (want['flowers and crop/crop'] > 0).any() and want['water/water'].min() < 1


# recorded on Apple silicon: numpy's float paths differ on other CPUs, so the physics drifts apart there (CI's x86)
@pytest.mark.skipif(platform.machine() != 'arm64', reason='golden trace recorded on arm64')
def test_every_body_dial_at_its_default_plays_the_games_it_played_before_the_body_existed():
    """The golden trace is what c37ac82's code did (golden_body.py says how it was made): the same fixed forager,
    seeds and worlds, a few hundred ticks of feeding, running out, nightfall and dawn, a reset and hatching."""
    want, got = np.load(GOLDEN), record(CONFIGS)
    assert sorted(got) == sorted(want.files)
    for key in want.files:
        if want[key].dtype.kind == 'f':
            np.testing.assert_allclose(got[key], want[key], rtol=1e-9, atol=1e-12, err_msg=key)
        else:
            assert np.array_equal(got[key], want[key]), key


def test_the_loader_is_still_strict_about_the_new_sections():
    data = SOLO.to_dict()
    data['fat']['stomach'] = 1
    with pytest.raises(ConfigError, match=r'config\.fat: unknown key\(s\) stomach'):
        build(Config, data)
    for bad in ({'keep': 0.0}, {'capacity': -1.0}, {'below': 2.0}):
        with pytest.raises(ConfigError):
            build(Config, {**SOLO.to_dict(), 'fat': {**SOLO.to_dict()['fat'], **bad}})
    with pytest.raises(ConfigError):
        build(Config, {**SOLO.to_dict(), 'energy': {**SOLO.to_dict()['energy'], 'work': -1.0}})


# fat

FAT = dict(capacity=0.3, keep=0.8, below=0.5, rate=0.02, heavy=0.0)


def feed(world, energy, fat=0.0):
    """The nim on a food, with this much energy and fat."""
    world.energy[:] = energy
    world.fat[:] = fat
    world.food_pos[0, 0] = world.pos[0, 0]
    world.food_regrow[0, 0] = 0


def test_food_past_a_full_bar_is_kept_as_fat_up_to_what_there_is_room_for():
    w = World(lone(food=1, fat=FAT, energy=dict(drain=0.0, move=0.0)), 1, 0)
    feed(w, 0.8)
    push(w)
    # 0.8 + 0.4 food = 1.2: the 0.2 over, 80% of it kept
    assert w.energy[0, 0] == pytest.approx(1.0) and w.fat[0, 0] == pytest.approx(0.16)
    # and the next food only has room for 0.14 more
    feed(w, 1.0, 0.16)
    push(w)
    assert w.energy[0, 0] == 1.0 and w.fat[0, 0] == pytest.approx(0.3)


def test_a_nim_with_a_full_bar_and_room_in_its_fat_eats_and_one_with_neither_doesnt():
    w = World(lone(food=1, fat=FAT, energy=dict(drain=0.0, move=0.0)), 1, 0)
    feed(w, 1.0, 0.0)
    push(w)
    assert not w.food_present[0, 0] and w.fat[0, 0] == pytest.approx(0.3)
    feed(w, 1.0, 0.3)
    push(w)
    assert w.food_present[0, 0]
    # fat off: a full bar leaves it alone, as it always did
    w = World(lone(food=1, energy=dict(drain=0.0, move=0.0)), 1, 0)
    feed(w, 1.0)
    push(w)
    assert w.food_present[0, 0] and w.fat[0, 0] == 0


def test_fat_turns_back_into_energy_below_the_line_at_the_set_rate():
    w = World(lone(fat=FAT, energy=dict(drain=0.0, move=0.0)), 1, 0)
    w.energy[:] = 0.3
    w.fat[:] = 0.2
    push(w, ticks=20)
    assert w.energy[0, 0] == pytest.approx(0.32) and w.fat[0, 0] == pytest.approx(0.18)
    # not above the line
    w.energy[:] = 0.5
    push(w, ticks=20)
    assert w.energy[0, 0] == pytest.approx(0.5) and w.fat[0, 0] == pytest.approx(0.18)
    # and it's what keeps a nim alive past its bar
    w = World(lone(fat=FAT, energy=dict(drain=0.02, move=0.0, start=0.01)), 1, 0)
    w.fat[:] = 0.3
    push(w, ticks=20 * 12)
    assert w.alive.all() and w.energy[0, 0] > 0
    w = World(lone(fat=FAT, energy=dict(drain=0.02, move=0.0, start=0.01)), 1, 0)
    push(w, ticks=20)
    assert not w.alive.any()


def test_grazing_fills_fat_once_the_bar_is_full_and_the_sense_reads_its_share():
    cfg = load(CONFIGS / 'nursery-grass.toml')
    cfg = replace(cfg, fat=replace(cfg.fat, **FAT), energy=replace(cfg.energy, drain=0.0))
    w = World(cfg, 1, 0)
    put(w, w.grass.pos[0, 0])
    w.energy[:] = 1.0
    push(w, ticks=40)
    assert w.fat[0, 0] > 0.1 and w.energy[0, 0] == 1.0
    me = observe(w, np.zeros((1, 1, 2))).me[0]
    assert me[SELF.index('fat')] == pytest.approx(w.fat[0, 0] / FAT['capacity'])
    assert observe(World(SOLO, 1, 0), np.zeros((1, 1, 2))).me[0, SELF.index('fat')] == 0


def test_a_cost_the_bar_cant_cover_isnt_forgiven_because_fat_trickles_in():
    # 0.25 a tick against a bar of 0.05 and fat that gives 0.001 a tick: it was clipped to 0 and then saved
    big = dict(drain=5.0, move=0.0, start=0.05)
    w = World(lone(fat=FAT, energy=big), 1, 0)
    w.fat[:] = 0.3
    push(w)
    assert not w.alive.any() and w.energy[0, 0] == 0 and w.died_of[0, 0] == STARVED
    # the same with fat off dies the same way
    w = World(lone(energy=big), 1, 0)
    push(w)
    assert not w.alive.any()
    # a cost the fat can cover still is: -0.0003 and 0.001 back
    small = dict(drain=0.01, move=0.0, start=0.0002)
    w = World(lone(fat=FAT, energy=small), 1, 0)
    w.fat[:] = 0.3
    push(w)
    assert w.alive.all() and w.energy[0, 0] == pytest.approx(0.0007) and w.fat[0, 0] == pytest.approx(0.299)


def test_a_jump_bigger_than_the_bar_isnt_forgiven_either():
    def jumper(fat, start):
        cfg = lone(fat=fat, energy=dict(drain=0.0, move=0.0, start=start), jump=dict(height=0.5, energy=0.4))
        w = World(cfg, 1, 0)
        w.fat[:] = 0.3
        x = np.zeros((1, 1, 8))
        x[..., 7] = 1.0
        w.step(x)
        return w
    assert not jumper(FAT, 0.1).alive.any()
    assert jumper(FAT, 0.5).alive.all()


def test_fat_on_a_survivor_never_carries_a_debt_into_the_next_tick():
    w = World(lone(fat=FAT, energy=dict(drain=0.4, move=0.0, start=0.2)), 1, 0)
    w.fat[:] = 0.3
    for _ in range(40):
        push(w)
        assert w.energy.min() >= 0


def eats(w):
    x = np.zeros((w.arenas, len(w.colony), 8))
    x[..., 3] = 1.0
    w.step(x)


def test_a_meal_from_the_crop_counts_what_the_bar_gained_not_what_went_to_fat():
    cfg = lone(fat=FAT, energy=dict(drain=0.0, move=0.0), crop=dict(capacity=2, start=0))
    w = World(cfg, 1, 0)
    w.crop[:] = 1
    w.energy[:] = 0.8
    eats(w)
    # 0.8 + 0.4 = 1.2: 0.2 into the bar's top, 80% of the other 0.2 kept
    assert w.energy[0, 0] == 1.0 and w.fat[0, 0] == pytest.approx(0.16)
    assert w.fed[0, 0] == pytest.approx(0.2) and w.nourished[0, 0] == pytest.approx(0.2)
    # a full bar gains nothing, and so is fed nothing
    w.crop[:] = 1
    eats(w)
    assert w.fed[0, 0] == pytest.approx(0.2) and w.fat[0, 0] == pytest.approx(0.3)
    # fat off, a meal that fits is counted whole
    w = World(lone(energy=dict(drain=0.0, move=0.0, start=0.5), crop=dict(capacity=2, start=0)), 1, 0)
    w.crop[:] = 1
    eats(w)
    assert w.fed[0, 0] == pytest.approx(0.4)


def test_a_flower_counts_what_the_bar_gained_not_what_went_to_fat():
    cfg = load(CONFIGS / 'colony-feast.toml')
    cfg = lone(cfg, fat=FAT, energy=dict(drain=0.0, move=0.0), flowers=dict(food=1))
    w = World(cfg, 1, 0)
    w.energy[:] = 0.8
    w.flower_pos[0, 0] = w.pos[0, 0]
    w.flower_left[0, 0] = 100
    w._drink()
    assert w.energy[0, 0] == 1.0 and w.fat[0, 0] == pytest.approx(0.16)
    assert w.fed[0, 0] == pytest.approx(0.2) and w.nourished[0, 0] == pytest.approx(0.2)


# resting and sleeping

def drained(w, ticks=20):
    before = w.energy[0, 0]
    push(w, ticks=ticks)
    return before - w.energy[0, 0]


def test_resting_costs_a_share_of_the_drain_and_walking_the_whole_of_it():
    base = dict(drain=0.02, move=0.0)
    full = World(lone(energy=base), 1, 0)
    rest = World(lone(energy=base | dict(rest=0.5)), 1, 0)
    assert drained(full) == pytest.approx(0.02)
    assert drained(rest) == pytest.approx(0.01)
    # thrust past `still` is walking
    rest = World(lone(energy=base | dict(rest=0.5, still=0.1)), 1, 0)
    before = rest.energy[0, 0]
    push(rest, thrust=0.5, ticks=20)
    assert before - rest.energy[0, 0] == pytest.approx(0.02)


def test_the_still_line_is_tireds_when_tired_is_on():
    cfg = lone(energy=dict(drain=0.02, move=0.0, rest=0.5, still=0.1), tired=dict(drain=0.01, rest=0.1, still=0.6, below=0.3, slowest=0.5))
    w = World(cfg, 1, 0)
    before = w.energy[0, 0]
    push(w, thrust=0.4, ticks=20)
    assert before - w.energy[0, 0] == pytest.approx(0.01)


def sleeper(**energy):
    cfg = lone(NIGHT, energy=dict(drain=0.02, move=0.0, rest=0.8, sleep=0.25) | energy, night=dict(cold=0.0))
    w = World(cfg, 1, 0)
    return w


def test_sleep_is_paid_instead_of_rest_in_the_dark_and_warm_only():
    w = sleeper()
    put(w, w.nests[0])
    # day, in the nest: resting
    assert drained(w) == pytest.approx(0.02 * 0.8)
    # night, in the nest: asleep
    at_night(w)
    assert drained(w) == pytest.approx(0.02 * 0.25)
    # night, out in the cold with nobody near: only resting
    put(w, w.nests[0] + (6.0, 0.0))
    assert drained(w) == pytest.approx(0.02 * 0.8)
    # and moving at night is moving
    put(w, w.nests[0])
    before = w.energy[0, 0]
    push(w, thrust=1.0, ticks=2)
    assert before - w.energy[0, 0] == pytest.approx(0.02 * 2 * DT)


def test_setting_rest_alone_makes_sleep_follow_it_and_an_explicit_sleep_overrides():
    cfg = lone(NIGHT, energy=dict(drain=0.02, move=0.0, rest=0.5, sleep=-1.0), night=dict(cold=0.0))
    w = World(cfg, 1, 0)
    put(w, w.nests[0])
    assert drained(w) == pytest.approx(0.01)
    at_night(w)
    assert drained(w) == pytest.approx(0.01)
    assert cfg.energy.asleep == 0.5
    # said out loud, sleep is its own: even 1, the whole drain
    w = World(replace(cfg, energy=replace(cfg.energy, sleep=1.0)), 1, 0)
    put(w, w.nests[0])
    at_night(w)
    assert drained(w) == pytest.approx(0.02)
    # a world file that leaves it out is the same as -1
    data = cfg.to_dict()
    del data['energy']['sleep']
    assert build(Config, data).energy.sleep == -1.0
    data['energy']['sleep'] = -2.0
    with pytest.raises(ConfigError, match='sleep'):
        build(Config, data)


def test_cold_is_charged_on_top_of_sleep_and_the_young_pay_their_share():
    cfg = lone(NIGHT, energy=dict(drain=0.02, move=0.0, sleep=0.25), night=dict(cold=0.05, nest=0.5), young=dict(seconds=100.0, energy=0.5, start=True))
    w = World(cfg, 1, 0)
    put(w, w.nests[0])
    at_night(w)
    push(w)
    # nest keeps half the cold off: only warm enough to sleep at 0.5
    assert w.energy[0, 0] == pytest.approx(cfg.energy.start - (0.02 * 0.25 + 0.05 * 0.5) * DT * 0.5)


# moving by weight

def test_moving_costs_by_mass_load_and_speed_and_nothing_standing_still():
    cfg = lone(energy=dict(drain=0.0, move=0.0, work=0.02), crop=dict(capacity=2, slow=0.0, start=2, mass=0.25), fat=FAT | dict(heavy=1.0))
    w = World(cfg, 1, 0)
    push(w, ticks=1)
    assert w.spent[0, 0] == 0
    push(w, thrust=1.0, ticks=30)
    before = w.spent[0, 0]
    push(w, thrust=1.0)
    speed = np.hypot(*w.vel[0, 0]) / cfg.creature.max_speed
    # body 1 kg and two foods at 0.25
    assert speed > 0.9
    assert w.spent[0, 0] - before == pytest.approx(0.02 * 1.5 * speed * DT)
    # a nim with its fat full weighs more, so the same speed costs more
    w.fat[:] = 0.3
    assert body.mass(w)[0, 0] == pytest.approx(1.8)
    before = w.spent[0, 0]
    push(w, thrust=1.0)
    speed = np.hypot(*w.vel[0, 0]) / cfg.creature.max_speed
    assert w.spent[0, 0] - before == pytest.approx(0.02 * 1.8 * speed * DT)


def test_what_it_carries_in_its_jaws_or_arms_adds_to_the_weight():
    cfg = lone(BLOCKS, food=3, energy=dict(work=0.02), crop=dict(capacity=2, mass=0.25))
    w = World(cfg, 1, 0)
    first = body.mass(w)[0, 0]
    assert first == pytest.approx(cfg.creature.mass)
    w.load[0, 0] = 1
    assert body.mass(w)[0, 0] == pytest.approx(first + 0.25)
    w.load[0, 0] = -1
    w.block_load[0, 0] = 0
    assert body.mass(w)[0, 0] == pytest.approx(first + cfg.block[0].mass)


# stamina

def test_stamina_comes_back_fastest_asleep_somewhere_warm():
    cfg = lone(NIGHT, energy=dict(drain=0.0, move=0.0),
               tired=dict(drain=0.01, rest=0.02, still=0.1, below=0.3, slowest=0.5, warm=2.0, dark=3.0), night=dict(cold=0.0))

    def gained(night, nest):
        w = World(cfg, 1, 0)
        put(w, w.nests[0] if nest else w.nests[0] + (6.0, 0.0))
        w.stamina[:] = 0.2
        if night:
            at_night(w)
        push(w, ticks=20)
        return w.stamina[0, 0] - 0.2

    assert gained(False, False) == pytest.approx(0.02)
    assert gained(False, True) == pytest.approx(0.04)
    assert gained(True, False) == pytest.approx(0.06)
    assert gained(True, True) == pytest.approx(0.12)


# the nest

def test_a_nest_grows_to_hold_its_colony_and_never_shrinks():
    # six places at 2 m² each: a circle of 12 m²
    want = np.sqrt(2.0 * COLONY.colonies.slots / np.pi)
    w = World(replace(COLONY, colonies=replace(COLONY.colonies, nest_area=2.0)), 2, 0)
    assert want > COLONY.colonies.nest_radius
    assert w.cfg.colonies.nest_radius == pytest.approx(want)
    # every reader sees it: standing just inside the grown nest is home, the replay header draws it, rays hit it
    put(w, w.nests[0] + (want - 0.1, 0.0))
    assert w.nest_at()[0, 0] == 0
    assert replay.header(w, 0, {})['info']['nests'][0]['radius'] == pytest.approx(want)
    small = World(replace(COLONY, colonies=replace(COLONY.colonies, nest_area=0.1)), 1, 0)
    assert small.cfg.colonies.nest_radius == COLONY.colonies.nest_radius
    # a colony with room to grow gets its room too
    roomy = World(replace(COLONY, colonies=replace(COLONY.colonies, nest_area=2.0, room=4)), 1, 0)
    assert roomy.cfg.colonies.nest_radius == pytest.approx(np.sqrt(2.0 * 10 / np.pi))


def test_a_nest_too_big_for_the_arena_is_refused():
    with pytest.raises(ConfigError, match='past the walls'):
        World(replace(COLONY, colonies=replace(COLONY.colonies, nest_area=500.0)), 1, 0)


# how they died

def dies(cfg, **state):
    w = World(cfg, 1, 0)
    for name, value in state.items():
        getattr(w, name)[:] = value
    push(w)
    return w


def test_a_nim_that_runs_dry_died_of_thirst_before_anything_else():
    w = dies(lone(WATER), water=0.0001, energy=0.00001, chill=0.9)
    assert not w.alive.any() and w.died_of[0, 0] == THIRST
    assert w.died_counts[0].tolist() == [0, 1, 0, 0]


def test_out_of_energy_while_chilled_through_is_chilled_and_otherwise_starved():
    cfg = lone(NIGHT, energy=dict(drain=0.01, move=0.0))
    w = dies(cfg, energy=0.00001, chill=0.8)
    assert w.died_of[0, 0] == CHILLED and w.died_counts[0, CHILLED] == 1
    w = dies(cfg, energy=0.00001, chill=0.1)
    assert w.died_of[0, 0] == STARVED and w.died_counts[0, STARVED] == 1
    # reset clears them, and the living have none
    w.reset(np.ones(1, bool))
    assert not w.died_of.any() and not w.died_counts.any()
    assert not World(cfg, 1, 0).died_of.any()


# the printed budget

def test_the_budget_reads_off_resting_sleeping_and_walking_with_and_without_fat():
    cfg = lone(energy=dict(drain=0.01, move=0.02, rest=0.5, sleep=0.2, work=0.01), crop=dict(capacity=2, slow=0.15, mass=0.25),
               fat=FAT | dict(heavy=1.0), creature=dict(mass=1.0, max_speed=2.0))
    b = costs(cfg)
    assert b['resting'] == pytest.approx(0.005) and b['asleep warm'] == pytest.approx(0.002)
    assert b['walking'] == pytest.approx(0.01 + 0.02 + 0.01 * 1.0)
    # laden: 1.5 kg at 70% of top speed
    assert b['walking laden'] == pytest.approx(0.01 + 0.02 + 0.01 * 1.5 * 0.7)
    assert b['walking, fat full'] == pytest.approx(0.01 + 0.02 + 0.01 * 1.3)
    assert b['walking laden, fat full'] == pytest.approx(0.01 + 0.02 + 0.01 * 1.8 * 0.7)
    text = show(cfg, budget(cfg, arenas=2))
    assert 'asleep warm' in text and 'walking laden, fat full' in text
    assert 'asleep warm' not in show(SOLO, budget(SOLO, arenas=2))


def test_a_block_it_holds_weighs_on_it_while_it_holds_on():
    vault = load(CONFIGS / 'vault.toml')
    cfg = lone(vault, energy=dict(work=0.02))
    door = next(k for k, b in enumerate(cfg.block) if b.mass < 10)
    w = World(cfg, 1, 0)
    block = cfg.block[door]
    put(w, w.physics.block_pos[0, door] - (block.w / 2 + 0.5, 0.0))
    x = np.zeros((1, 1, 8))
    x[..., 5] = 1
    w.step(x)
    assert body.mass(w)[0, 0] == pytest.approx(cfg.creature.mass + block.mass)
