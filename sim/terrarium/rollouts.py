# Rollouts, optionally split over processes. Each share of the arenas has its own
# World and a CPU copy of the actor, plays its part of every rollout, and the
# parts are joined along the sample axis. One worker plays in this process with
# the run's seed, the same as before there were workers; with more, worker i's
# world and sampling are seeded from (seed, i), so a run is repeatable for a given count.
# Arenas of other worlds (mix) play beside them, one share per world, so a brain keeps what it can do there.
#
# OnDevice splits it the other way: the workers only step their worlds, and the brain runs once a step for all of
# them on the learner's device. A wide brain on the CPU is most of a rollout's time; on a GPU it's a few
# milliseconds a step. With one worker and the brain on the CPU it plays exactly what Collector does.
#
# OnDevice can also play several brains against each other, one per colony: brain k plays colony (k + arena) mod
# the number of brains, so across the arenas every brain takes every seat. `whose` says which brain each sample is.
#
# A brain with memory carries each creature's notes from one rollout into the next, as its life goes on.

import multiprocessing as mp

import numpy as np
import torch

from .brain import Brain, tensors
from .config import Config, Train
from .forage import Forage, Observation
from .ppo import Episodes, Rollout, collect, kept


def seeds(seed: int, parts: int, workers: int) -> list[int]:
    """Each share's seed, as Collector gives them: with one worker its own share has the run's seed."""
    own = lambda i: int(np.random.SeedSequence([seed, i]).generate_state(1)[0])
    return [seed if i == 0 and workers == 1 else own(i) for i in range(parts)]


class Share:
    def __init__(self, cfg: Config, train: Train, arenas: int, seed: int, actor: Brain):
        self.env = Forage(cfg, train, arenas, seed)
        self.actor = actor
        self.episodes = Episodes(self.env.samples, cfg.dt * train.ppo.repeat)
        self.obs = self.env.observe()
        self.notes = actor.blank(self.env.samples)

    def play(self, state: dict, steps: int) -> tuple[Rollout, np.ndarray, list]:
        """Load the learner's weights, play a rollout, and hand back the value after it and finished episodes."""
        self.actor.load_state_dict(state)
        roll, self.obs, self.notes = collect(self.env, self.actor, steps, self.obs, self.episodes, self.notes)
        with torch.no_grad():
            last_value = self.actor(*tensors(self.obs, 'cpu'), self.notes)[1].numpy()
        finished, self.episodes.finished = self.episodes.finished, []
        return roll, last_value, finished


def serve(conn, cfg: Config, train: Train, arenas: int, seed: int, actor: Brain):
    # the workers between them use the cores; threads inside each would only fight
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    share = Share(cfg, train, arenas, seed, actor)
    while (job := conn.recv()) is not None:
        try:
            conn.send(share.play(*job))
        except Exception as e:
            conn.send(e)
            raise


class Collector:
    def __init__(self, cfg: Config, train: Train, arenas: int, seed: int, actor: Brain, workers: int = 1,
                 mix: list[tuple[Config, int]] | None = None):
        mix = mix or []
        self.samples = sum(n * c.colonies.count * c.colonies.slots for c, n in [(cfg, arenas), *mix])
        self.episodes = Episodes(self.samples, cfg.dt * train.ppo.repeat)
        self.local, self.pipes, self.procs = [], [], []
        if workers == 1:
            parts = [(cfg, arenas), *mix]
            self.local = [Share(c, train, n, s, actor) for (c, n), s in zip(parts, seeds(seed, len(parts), 1))]
            return
        parts = [(cfg, len(a)) for a in np.array_split(np.arange(arenas), workers)] + mix
        own = seeds(seed, len(parts), workers)
        # spawn, not fork: a forked child of a process holding CUDA or MPS can hang
        ctx = mp.get_context('spawn')
        for i, (c, n) in enumerate(parts):
            mine, theirs = ctx.Pipe()
            proc = ctx.Process(target=serve, args=(theirs, c, train, n, own[i], actor), daemon=True)
            proc.start()
            self.pipes.append(mine)
            self.procs.append(proc)

    def collect(self, state: dict, steps: int) -> tuple[Rollout, np.ndarray]:
        """A rollout from every share, joined, and the value of the observation after it."""
        state = {k: v.cpu() for k, v in state.items()}
        if self.local:
            parts = [share.play(state, steps) for share in self.local]
        else:
            for pipe in self.pipes:
                pipe.send((state, steps))
            try:
                parts = [pipe.recv() for pipe in self.pipes]
            except EOFError:
                raise RuntimeError('a rollout worker died; its traceback is above') from None
            for p in parts:
                if isinstance(p, Exception):
                    raise RuntimeError('a rollout worker failed') from p
        for _, _, finished in parts:
            self.episodes.finished += finished
        rolls = [p[0] for p in parts]
        roll = Rollout(**{k: np.concatenate([getattr(r, k) for r in rolls], axis=1)
                          for k in Rollout.__dataclass_fields__})
        return roll, np.concatenate([p[1] for p in parts])

    def close(self):
        for pipe in self.pipes:
            pipe.send(None)
        for proc in self.procs:
            proc.join(timeout=10)


def stepped(env: Forage, actions: np.ndarray) -> tuple:
    obs, reward, done, _ = env.step(actions)
    return obs, reward, done, env.active, env.final, env.cut, env.hint


def simulate(conn, cfg: Config, train: Train, arenas: int, seed: int):
    env = Forage(cfg, train, arenas, seed)
    conn.send((env.observe(), env.active, env.hint))
    while (actions := conn.recv()) is not None:
        try:
            conn.send(stepped(env, actions))
        except Exception as e:
            conn.send(e)
            raise


class Here:
    """A share of the worlds stepped in this process, with the calls a worker's has."""

    def __init__(self, cfg: Config, train: Train, arenas: int, seed: int):
        self.env = Forage(cfg, train, arenas, seed)
        self.actions = np.zeros(0)

    def first(self):
        return self.env.observe(), self.env.active, self.env.hint

    def send(self, actions: np.ndarray):
        self.actions = actions

    def recv(self):
        return stepped(self.env, self.actions)


class There:
    """A share of the worlds stepped in a worker process."""

    def __init__(self, ctx, cfg: Config, train: Train, arenas: int, seed: int):
        self.pipe, theirs = ctx.Pipe()
        self.proc = ctx.Process(target=simulate, args=(theirs, cfg, train, arenas, seed), daemon=True)
        self.proc.start()

    def first(self):
        return self.recv()

    def send(self, actions: np.ndarray):
        self.pipe.send(actions)

    def recv(self):
        try:
            got = self.pipe.recv()
        except EOFError:
            raise RuntimeError('a world worker died; its traceback is above') from None
        if isinstance(got, Exception):
            raise RuntimeError('a world worker failed') from got
        return got

    def close(self):
        self.pipe.send(None)
        self.proc.join(timeout=10)


def join(parts: list[Observation]) -> Observation:
    return Observation(*(np.concatenate(x) for x in zip(*((o.me, o.kinds, o.rays) for o in parts))))


def seats(parts: list[tuple[Config, int]], brains: int, fixed: bool = False) -> np.ndarray:
    """Which brain plays each sample: colony (k + arena) mod brains is brain k's, arenas counted over every part, so
    every brain takes every seat; fixed, colony k is always brain k's (mod brains), as when a game's sides differ."""
    out, first = [], 0
    for c, n in parts:
        colony = np.repeat(np.arange(c.colonies.count), c.colonies.slots)
        arena = np.arange(first, first + n)[:, None] * (not fixed)
        out.append(((colony[None] - arena) % brains).reshape(-1))
        first += n
    return np.concatenate(out)


class OnDevice:
    def __init__(self, cfg: Config, train: Train, arenas: int, seed: int, actor: Brain | list[Brain], workers: int = 1,
                 mix: list[tuple[Config, int]] | None = None, device: str = 'cpu', fixed: bool = False):
        mix = mix or []
        parts = ([(cfg, arenas)] if workers == 1 else
                 [(cfg, len(a)) for a in np.array_split(np.arange(arenas), workers)]) + mix
        sizes = [n * c.colonies.count * c.colonies.slots for c, n in parts]
        self.samples = sum(sizes)
        self.ends = np.cumsum(sizes)[:-1]
        self.episodes = Episodes(self.samples, cfg.dt * train.ppo.repeat)
        self.gamma = train.ppo.gamma
        self.actors = [a.to(device) for a in (actor if isinstance(actor, list) else [actor])]
        self.actor, self.device = self.actors[0], device
        if len(self.actors) > 1 and any(a.memory for a in self.actors):
            raise ValueError("rivals with memory aren't written yet")
        self.notes = self.actor.blank(self.samples)
        self.whose = seats(parts, len(self.actors), fixed)
        self.by_brain = [Episodes(self.samples, cfg.dt * train.ppo.repeat) for _ in self.actors]
        mine = seeds(seed, len(parts), workers)
        if workers == 1:
            self.shares = [Here(c, train, n, s) for (c, n), s in zip(parts, mine)]
        else:
            # spawn, not fork: a forked child of a process holding CUDA or MPS can hang
            ctx = mp.get_context('spawn')
            self.shares = [There(ctx, c, train, n, s) for (c, n), s in zip(parts, mine)]
        first = [s.first() for s in self.shares]
        self.obs = join([f[0] for f in first])
        self.active = np.concatenate([f[1] for f in first])
        self.hint = np.concatenate([f[2] for f in first])

    def _value(self, obs: Observation, notes: torch.Tensor) -> torch.Tensor:
        if len(self.actors) == 1:
            return self.actor(*tensors(obs, self.device), notes)[1]
        value = torch.zeros(len(obs.me), device=self.device)
        for k, actor in enumerate(self.actors):
            mine = torch.from_numpy(self.whose == k).to(self.device)
            value[mine] = actor(*tensors(self._part(obs, k), self.device))[1]
        return value

    def _part(self, obs: Observation, k: int) -> Observation:
        mine = self.whose == k
        return Observation(obs.me[mine], obs.kinds[mine], obs.rays[mine])

    def _act(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Each brain's actions, log odds and values for its own samples."""
        if len(self.actors) == 1:
            mean, value, self.notes = self.actor(*tensors(self.obs, self.device), self.notes)
            dist = self.actor.dist(mean)
            action = dist.sample()
            return action.cpu().numpy(), dist.log_prob(action).sum(-1).cpu().numpy(), value.cpu().numpy()
        actions = np.zeros((self.samples, len(self.actor.schema['actions'])), np.float32)
        logps, values = np.zeros(self.samples, np.float32), np.zeros(self.samples, np.float32)
        for k, actor in enumerate(self.actors):
            mine = self.whose == k
            mean, value, _ = actor(*tensors(self._part(self.obs, k), self.device))
            dist = actor.dist(mean)
            action = dist.sample()
            actions[mine], values[mine] = action.cpu().numpy(), value.cpu().numpy()
            logps[mine] = dist.log_prob(action).sum(-1).cpu().numpy()
        return actions, logps, values

    def collect(self, state: dict | list[dict], steps: int) -> tuple[Rollout, np.ndarray]:
        for actor, s in zip(self.actors, state if isinstance(state, list) else [state]):
            actor.load_state_dict(s)
        keep: dict[str, list] = {k: [] for k in Rollout.__dataclass_fields__ if k != 'notes'}
        start = self.notes.cpu().numpy()[None]
        with torch.no_grad():
            for _ in range(steps):
                actions, logps, values = self._act()
                for share, a in zip(self.shares, np.split(actions, self.ends)):
                    share.send(a)
                # while the worlds step
                for k, v in (('me', self.obs.me), ('kinds', self.obs.kinds), ('rays', self.obs.rays)):
                    keep[k].append(v)
                keep['actions'].append(actions)
                keep['logprobs'].append(logps)
                keep['values'].append(values)
                keep['active'].append(self.active)
                keep['hints'].append(self.hint)
                got = [share.recv() for share in self.shares]
                reward, done = np.concatenate([g[1] for g in got]), np.concatenate([g[2] for g in got])
                self.episodes.add(reward, done, self.active)
                if len(self.actors) > 1:
                    for k, episodes in enumerate(self.by_brain):
                        episodes.add(reward, done, self.active & (self.whose == k))
                if any(g[4] is not None for g in got):
                    # cut off by the time limit: what's left is worth what the value says (shares that weren't
                    # cut have none, and count nothing)
                    after = self._value(join([g[0] if g[4] is None else g[4] for g in got]), self.notes)
                    reward = reward + self.gamma * after.cpu().numpy() * np.concatenate([g[5] for g in got])
                keep['rewards'].append(reward)
                keep['dones'].append(done)
                self.notes = kept(self.notes, self.active, done)
                self.obs = join([g[0] for g in got])
                self.active = np.concatenate([g[3] for g in got])
                self.hint = np.concatenate([g[6] for g in got])
            last_value = self._value(self.obs, self.notes).cpu().numpy()
        return Rollout(**{k: np.stack(v) for k, v in keep.items()}, notes=start), last_value

    def close(self):
        for share in self.shares:
            if isinstance(share, There):
                share.close()
