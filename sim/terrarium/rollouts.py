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

import multiprocessing as mp

import numpy as np
import torch

from .brain import Brain, tensors
from .config import Config, Train
from .forage import Forage, Observation
from .ppo import Episodes, Rollout, collect


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

    def play(self, state: dict, steps: int) -> tuple[Rollout, np.ndarray, list]:
        """Load the learner's weights, play a rollout, and hand back the value after it and finished episodes."""
        self.actor.load_state_dict(state)
        roll, self.obs = collect(self.env, self.actor, steps, self.obs, self.episodes)
        with torch.no_grad():
            last_value = self.actor(*tensors(self.obs, 'cpu'))[1].numpy()
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
        self.samples = sum(n * c.colonies.count * c.colonies.size for c, n in [(cfg, arenas), *mix])
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
    return obs, reward, done, env.active, env.final, env.cut


def simulate(conn, cfg: Config, train: Train, arenas: int, seed: int):
    env = Forage(cfg, train, arenas, seed)
    conn.send((env.observe(), env.active))
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
        return self.env.observe(), self.env.active

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


class OnDevice:
    def __init__(self, cfg: Config, train: Train, arenas: int, seed: int, actor: Brain, workers: int = 1,
                 mix: list[tuple[Config, int]] | None = None, device: str = 'cpu'):
        mix = mix or []
        parts = ([(cfg, arenas)] if workers == 1 else
                 [(cfg, len(a)) for a in np.array_split(np.arange(arenas), workers)]) + mix
        sizes = [n * c.colonies.count * c.colonies.size for c, n in parts]
        self.samples = sum(sizes)
        self.ends = np.cumsum(sizes)[:-1]
        self.episodes = Episodes(self.samples, cfg.dt * train.ppo.repeat)
        self.gamma = train.ppo.gamma
        self.actor, self.device = actor.to(device), device
        mine = seeds(seed, len(parts), workers)
        if workers == 1:
            self.shares = [Here(c, train, n, s) for (c, n), s in zip(parts, mine)]
        else:
            # spawn, not fork: a forked child of a process holding CUDA or MPS can hang
            ctx = mp.get_context('spawn')
            self.shares = [There(ctx, c, train, n, s) for (c, n), s in zip(parts, mine)]
        first = [s.first() for s in self.shares]
        self.obs = join([o for o, _ in first])
        self.active = np.concatenate([a for _, a in first])

    def _value(self, obs: Observation) -> torch.Tensor:
        return self.actor(*tensors(obs, self.device))[1]

    def collect(self, state: dict, steps: int) -> tuple[Rollout, np.ndarray]:
        self.actor.load_state_dict(state)
        keep: dict[str, list] = {k: [] for k in Rollout.__dataclass_fields__}
        with torch.no_grad():
            for _ in range(steps):
                mean, value = self.actor(*tensors(self.obs, self.device))
                dist = self.actor.dist(mean)
                action = dist.sample()
                actions = action.cpu().numpy()
                for share, a in zip(self.shares, np.split(actions, self.ends)):
                    share.send(a)
                # while the worlds step
                for k, v in (('me', self.obs.me), ('kinds', self.obs.kinds), ('rays', self.obs.rays)):
                    keep[k].append(v)
                keep['actions'].append(actions)
                keep['logprobs'].append(dist.log_prob(action).sum(-1).cpu().numpy())
                keep['values'].append(value.cpu().numpy())
                keep['active'].append(self.active)
                got = [share.recv() for share in self.shares]
                reward, done = np.concatenate([g[1] for g in got]), np.concatenate([g[2] for g in got])
                self.episodes.add(reward, done, self.active)
                if any(g[4] is not None for g in got):
                    # cut off by the time limit: what's left is worth what the value says (shares that weren't
                    # cut have none, and count nothing)
                    after = self._value(join([g[0] if g[4] is None else g[4] for g in got]))
                    reward = reward + self.gamma * after.cpu().numpy() * np.concatenate([g[5] for g in got])
                keep['rewards'].append(reward)
                keep['dones'].append(done)
                self.obs = join([g[0] for g in got])
                self.active = np.concatenate([g[3] for g in got])
            last_value = self._value(self.obs).cpu().numpy()
        return Rollout(**{k: np.stack(v) for k, v in keep.items()}), last_value

    def close(self):
        for share in self.shares:
            if isinstance(share, There):
                share.close()
