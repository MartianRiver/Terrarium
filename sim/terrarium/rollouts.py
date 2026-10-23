# Rollouts, optionally split over processes. Each share of the arenas has its own
# World and a CPU copy of the actor, plays its part of every rollout, and the
# parts are joined along the sample axis. One worker plays in this process with
# the run's seed, the same as before there were workers; with more, worker i's
# world and sampling are seeded from (seed, i), so a run is repeatable for a given count.

import multiprocessing as mp

import numpy as np
import torch

from .brain import Brain, tensors
from .config import Config, Reward
from .forage import Forage
from .ppo import Episodes, Rollout, collect


class Share:
    def __init__(self, cfg: Config, reward: Reward, arenas: int, seed: int, actor: Brain):
        self.env = Forage(cfg, reward, arenas, seed)
        self.actor = actor
        self.episodes = Episodes(self.env.samples, cfg.dt)
        self.obs = self.env.observe()

    def play(self, state: dict, steps: int) -> tuple[Rollout, np.ndarray, list]:
        """Load the learner's weights, play a rollout, and hand back the value after it and finished episodes."""
        self.actor.load_state_dict(state)
        roll, self.obs = collect(self.env, self.actor, steps, self.obs, self.episodes)
        with torch.no_grad():
            last_value = self.actor(*tensors(self.obs, 'cpu'))[1].numpy()
        finished, self.episodes.finished = self.episodes.finished, []
        return roll, last_value, finished


def serve(conn, cfg: Config, reward: Reward, arenas: int, seed: int, actor: Brain):
    # the workers between them use the cores; threads inside each would only fight
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    share = Share(cfg, reward, arenas, seed, actor)
    while (job := conn.recv()) is not None:
        try:
            conn.send(share.play(*job))
        except Exception as e:
            conn.send(e)
            raise


class Collector:
    def __init__(self, cfg: Config, reward: Reward, arenas: int, seed: int, actor: Brain, workers: int = 1):
        self.samples = arenas * cfg.colonies.count * cfg.colonies.size
        self.episodes = Episodes(self.samples, cfg.dt)
        self.local, self.pipes, self.procs = None, [], []
        if workers == 1:
            self.local = Share(cfg, reward, arenas, seed, actor)
            return
        # spawn, not fork: a forked child of a process holding CUDA or MPS can hang
        ctx = mp.get_context('spawn')
        for i, n in enumerate(len(a) for a in np.array_split(np.arange(arenas), workers)):
            mine, theirs = ctx.Pipe()
            own = int(np.random.SeedSequence([seed, i]).generate_state(1)[0])
            proc = ctx.Process(target=serve, args=(theirs, cfg, reward, n, own, actor), daemon=True)
            proc.start()
            self.pipes.append(mine)
            self.procs.append(proc)

    def collect(self, state: dict, steps: int) -> tuple[Rollout, np.ndarray]:
        """A rollout from every share, joined, and the value of the observation after it."""
        if self.local is not None:
            parts = [self.local.play(state, steps)]
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
