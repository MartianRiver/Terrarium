# [arena] maze: the arena is a maze × maze grid of rooms, and each episode its blocks become the inner walls of a new
# maze, carved by a random depth-first walk, so there's exactly one way between any two rooms and no layout repeats
# often enough to learn by heart. Every such maze has (maze - 1)² inner walls, which is how many blocks the world sets
# (each a room long, less a wall's thickness, so walls meeting at a corner don't push each other apart).
import numpy as np

from .config import ConfigError


def check(cfg):
    n = cfg.arena.maze
    if n < 2:
        raise ConfigError(f'arena.maze is {n}: a maze needs at least 2 rooms a side')
    if len(cfg.block) != (n - 1) ** 2:
        raise ConfigError(f'a {n}×{n} maze has {(n - 1) ** 2} inner walls, and [[block]] has {len(cfg.block)}')
    if cfg.arena.scatter or cfg.smell.on or any(b.carry or b.shut for b in cfg.block):
        raise ConfigError('maze walls are placed by the maze: not with scatter, smell, carry or shut')


def walls(n: int, rng: np.random.Generator, opened: set | None = None) -> list[tuple[float, float, float]]:
    """A new maze's inner walls as (x, y, angle), x and y in rooms from the arena's corner; the ways between rooms
    ((row, col) pairs) go into opened."""
    seen = np.zeros((n, n), bool)
    opened = set() if opened is None else opened
    start = (int(rng.integers(n)), int(rng.integers(n)))
    seen[start] = True
    path = [start]
    while path:
        r, c = path[-1]
        ways = [(r + dr, c + dc) for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))
                if 0 <= r + dr < n and 0 <= c + dc < n and not seen[r + dr, c + dc]]
        if not ways:
            path.pop()
            continue
        nxt = ways[rng.integers(len(ways))]
        seen[nxt] = True
        opened.add(frozenset(((r, c), nxt)))
        path.append(nxt)
    out = []
    for r in range(n):
        for c in range(n):
            if c + 1 < n and frozenset(((r, c), (r, c + 1))) not in opened:
                out.append((c + 1.0, r + 0.5, np.pi / 2))
            if r + 1 < n and frozenset(((r, c), (r + 1, c))) not in opened:
                out.append((c + 0.5, r + 1.0, 0.0))
    return out


def carve(world, idx: np.ndarray):
    n, size = world.cfg.arena.maze, world.cfg.arena.size
    room = size / n
    every = list(range(len(world.cfg.block)))
    for a in idx:
        world.maze_open[a] = set()
        w = walls(n, world.rng, world.maze_open[a])
        to = np.array([(x * room - size / 2, y * room - size / 2) for x, y, _ in w])
        world.physics.shift([a], every, to, np.array([t for *_, t in w]))


def mapped_policy(world):
    """A baseline that knows the maze and where the berry is: the shortest way there, room by room, through the
    middle of each gap. About the best any searcher could do."""
    n, size = world.cfg.arena.maze, world.cfg.arena.size
    room = size / n

    def where(p):
        return tuple(np.clip(((p[::-1] + size / 2) // room).astype(int), 0, n - 1))     # (row, col)

    def centre(rc):
        return np.array([(rc[1] + 0.5) * room - size / 2, (rc[0] + 0.5) * room - size / 2])

    def first_step(a, start, goal):
        before, todo = {start: None}, [start]
        while todo:
            here = todo.pop(0)
            if here == goal:
                break
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                q = (here[0] + dr, here[1] + dc)
                if q not in before and frozenset((here, q)) in world.maze_open[a]:
                    before[q] = here
                    todo.append(q)
        step = goal
        while before.get(step) not in (start, None):
            step = before[step]
        return step

    def act(w):
        out = np.zeros((*w.alive.shape, 7))
        out[..., 2:] = -1
        for a in range(w.alive.shape[0]):
            food = np.flatnonzero(w.food_present[a, :w.wild])
            for i in range(w.alive.shape[1]):
                if not len(food):
                    continue
                me = w.pos[a, i]
                berry = w.food_pos[a, food[np.hypot(*(w.food_pos[a, food] - me).T).argmin()]]
                here, there = where(me), where(berry)
                target = berry
                if here != there:
                    nxt = first_step(a, here, there)
                    door = (centre(here) + centre(nxt)) / 2
                    target = door if np.hypot(*(door - me)) > 0.6 else centre(nxt)
                d = target - me
                bearing = (np.arctan2(d[1], d[0]) - w.heading[a, i] + np.pi) % (2 * np.pi) - np.pi
                out[a, i, 0] = 1.0 if abs(bearing) < 1 else 0.2
                out[a, i, 1] = np.clip(bearing * 3, -1, 1)
        return out
    return act


def wall_policy(world):
    """A baseline with no memory: keep a wall on the left (go left when it opens up, right when the way ahead is
    shut), and go for a berry once one's in sight. Finds everything in a maze like these, eventually, by walking
    every corridor in turn."""
    from .vision import BLOCK, FOOD, WALL, angles, look
    a = angles(world.cfg.vision)
    ahead = np.abs(a) < 0.3
    left = (a > 1.2) & (a < 1.9)

    def act(w):
        sight = look(w)
        solid = (sight.kind == WALL) | (sight.kind == BLOCK)
        front = np.where(ahead & solid, sight.dist, np.inf).min(-1)
        side = np.where(left & solid, sight.dist, np.inf).min(-1)
        food = np.where(sight.kind == FOOD, sight.dist, np.inf)
        sees = np.isfinite(food.min(-1))
        turn = np.where(front < 1.4, -1.0, np.where(side > 2.0, 0.8, np.where(side < 0.9, -0.4, 0.0)))
        turn = np.where(sees, np.clip(a[food.argmin(-1)] * 3, -1, 1), turn)
        thrust = np.where((front < 1.0) & ~sees, 0.2, 1.0)
        out = np.full((*w.alive.shape, 7), -1.0)
        out[..., 0], out[..., 1] = thrust, turn
        return out
    return act


class Visits:
    """Which rooms each creature has been in this episode, for a side job that asks the notes "have I been here
    before?" (loop closure, Mirowski et al. 2016): 1 once a creature comes back into a room it left, 0 on its first
    time in. The brain never sees it; it's only a label to learn from."""

    def __init__(self, world):
        self.world = world
        n = world.cfg.arena.maze
        self.entries = np.zeros((*world.alive.shape, n, n), int)
        self.room = np.full((*world.alive.shape, 2), -1)

    def reset(self, arenas: np.ndarray):
        self.entries[arenas] = 0
        self.room[arenas] = -1

    def update(self) -> np.ndarray:
        """After a step: been here before, (arenas * creatures,)."""
        w = self.world
        n, size = w.cfg.arena.maze, w.cfg.arena.size
        rc = np.clip(((w.pos[..., ::-1] + size / 2) // (size / n)).astype(int), 0, n - 1)
        moved = (rc != self.room).any(-1)
        a, c = np.nonzero(moved)
        self.entries[a, c, rc[a, c, 0], rc[a, c, 1]] += 1
        self.room = rc
        here = np.take_along_axis(self.entries.reshape(*rc.shape[:2], -1), (rc[..., 0] * n + rc[..., 1])[..., None], -1)
        return (here[..., 0] > 1).reshape(-1).astype(np.float32)
