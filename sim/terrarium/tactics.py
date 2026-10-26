# What the sprint and the flowers get used for, in evals. Away from its own nest, a Terrikin always has a best
# reason it could sprint: a flower in view, food in view, a run home it needs (hungry with jelly there, a full crop,
# or dusk falling, while facing home), or none of those (just getting about). How often it says yes when ready, and
# which reason each sprint started under, show whether sprints go where they pay or get spent on travel; a sprint
# paid off if it ate, drank or got home within PAY seconds of starting. Flowers: how many opened, and how often one
# in view was headed for, and meals a minute away from home with the boost on and off.
import numpy as np

from .world import World

REASONS = ('flower', 'food', 'home', 'about')
PAY = 3.0
# heading at something: within this of straight ahead
AIM = np.pi / 6
SPRINT = 4


def wrap(a: np.ndarray) -> np.ndarray:
    return (a + np.pi) % (2 * np.pi) - np.pi


def in_view(w: World, pos: np.ndarray, present: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(arenas, creatures, things): each present thing within its field and range of view (blocked or not), and
    how far off straight ahead it is."""
    d = pos[:, None] - w.pos[:, :, None]
    off = wrap(np.arctan2(d[..., 1], d[..., 0]) - w.heading[..., None])
    v = w.cfg.vision
    seen = (np.hypot(d[..., 0], d[..., 1]) < v.range) & (np.abs(off) <= v.fov / 2) & present[:, None]
    return seen, off


def flower_in_view(w: World) -> np.ndarray:
    return in_view(w, w.flower_pos, w.flowers_open)[0].any(-1)


def reason(w: World, nest: np.ndarray, mine: np.ndarray) -> np.ndarray:
    """(arenas, creatures): the index in REASONS of the best reason to sprint, -1 in its own nest."""
    home = w.nests[w.colony] - w.pos
    facing = np.abs(wrap(np.arctan2(home[..., 1], home[..., 0]) - w.heading)) < AIM
    evening = ((w.light() < 1) & ~w.dark)[:, None]
    needs = ((w.energy < w.cfg.jelly.hunger) & (mine > 0)) | (w.crop >= w.cfg.crop.capacity) | evening
    food = in_view(w, w.food_pos, w.food_present)[0].any(-1)
    why = np.select([flower_in_view(w), food, needs & facing], [0, 1, 2], 3)
    return np.where(nest == w.colony, -1, why)


class Tactics:
    """Counts kept over an eval: watch() before each step, after() once it's taken."""

    def __init__(self, w: World):
        shape = w.alive.shape
        self.on = w.cfg.sprint.on
        self.pay = round(PAY * w.cfg.tick_hz)
        self.hz = w.cfg.tick_hz
        self.ready, self.yes, self.started, self.paid = (np.zeros(len(REASONS), int) for _ in range(4))
        self.out = 0
        # per creature: the reason its last sprint started under, and ticks left for it to pay
        self.why, self.left = np.full(shape, -1), np.zeros(shape, int)
        self.opened, self.drunk, self.looking, self.aimed = 0, 0, 0, 0
        # ticks away from home and meals there, without the boost and with it
        self.boost_ticks, self.boost_meals = np.zeros(2, int), np.zeros(2, int)

    def watch(self, w: World, before: np.ndarray, nest: np.ndarray, mine: np.ndarray, action: np.ndarray):
        why = np.where(before, reason(w, nest, mine), -1)
        self.out += (why >= 0).sum()
        boosted = (why >= 0) & (w.nectar > 0)
        self.boost_ticks += (why >= 0).sum() - boosted.sum(), boosted.sum()
        if self.on and action.shape[-1] > SPRINT:
            ready = (why >= 0) & (w.sprinting == 0) & (w.resting == 0)
            self.ready += np.bincount(why[ready], minlength=len(REASONS))
            self.yes += np.bincount(why[ready & (action[..., SPRINT] > 0)], minlength=len(REASONS))
        seen, off = in_view(w, w.flower_pos, w.flowers_open)
        looking = before & seen.any(-1)
        self.looking += looking.sum()
        self.aimed += (looking & (seen & (np.abs(off) < AIM)).any(-1) & (action[..., 0] > 0.5)).sum()
        self.last = (before, why, w.sprinting.copy(), w.meals.copy(), w.drunk.copy(), nest == w.colony,
                     w.flowers_open.copy(), boosted)

    def after(self, w: World, done: np.ndarray):
        before, why, sprinting, meals, drunk, home, opened, boosted = self.last
        go = before & (why >= 0) & (sprinting == 0) & (w.sprinting > 0)
        self.started += np.bincount(why[go], minlength=len(REASONS))
        self.why[go], self.left[go] = why[go], self.pay
        won = before & ((w.meals > meals) | (w.drunk > drunk) | ((w.nest_at() == w.colony) & ~home))
        hit = won & (self.left > 0)
        self.paid += np.bincount(self.why[hit], minlength=len(REASONS))
        self.left[hit] = 0
        self.left = np.maximum(self.left - 1, 0)
        self.opened += (w.flowers_open & ~opened & ~done[:, None]).sum()
        self.drunk += (before & (w.drunk > drunk)).sum()
        ate = (why >= 0) & (w.meals > meals)
        self.boost_meals += (ate & ~boosted).sum(), (ate & boosted).sum()

    def result(self) -> dict:
        def share(a, b):
            return float(a / b) if b else None
        sprints = None
        if self.on:
            sprints = {'per_minute_out': share(self.started.sum(), self.out / self.hz / 60),
                       **{r: {'yes': share(self.yes[i], self.ready[i]), 'share': share(self.started[i], self.started.sum()),
                              'paid': share(self.paid[i], self.started[i])} for i, r in enumerate(REASONS)}}
        return {'sprints': sprints, 'flower_use': {'opened': int(self.opened), 'drunk': share(self.drunk, self.opened),
                                                  'chased': share(self.aimed, self.looking)},
                'nectar': {'meals_a_minute': share(self.boost_meals[1], self.boost_ticks[1] / self.hz / 60),
                           'without': share(self.boost_meals[0], self.boost_ticks[0] / self.hz / 60)}}
