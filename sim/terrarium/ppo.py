# PPO, shaped after CleanRL's continuous-action version: collect a rollout on
# the CPU, work out advantages with GAE, then a few clipped passes over it on
# the learner's device. Each creature in each arena is one sample stream.
#
# A brain with memory learns from whole streams instead of shuffled samples: each pass replays a stream's choices in
# order from the notes it had at the rollout's start, so what it learns to write down is paid for by what that does
# for its choices later in the rollout (backpropagation through time, as CleanRL's LSTM PPO does it). With
# [ppo] side it also gets a side job (Side) that pays the notes for holding the past before anything else does.

from dataclasses import dataclass

import numpy as np
import torch
from torch import nn

from .brain import Brain, tensors
from .config import PPO
from .forage import Forage, Observation


@dataclass
class Rollout:
    me: np.ndarray        # (steps, samples, ...) as in Observation
    kinds: np.ndarray
    rays: np.ndarray
    actions: np.ndarray   # what was sampled, before clipping
    logprobs: np.ndarray
    values: np.ndarray
    rewards: np.ndarray
    dones: np.ndarray     # this step ended the episode; the next observation is a fresh start
    active: np.ndarray    # the creature was alive to act; the dead wait for their arena to start over
    hints: np.ndarray     # a side job's label for what was seen (Forage.hint)
    notes: np.ndarray     # (1, samples, memory): each stream's notes at the rollout's start


class Episodes:
    """Running return and length per sample stream, and the episodes that finished since last asked."""

    def __init__(self, samples: int, dt: float):
        self.dt = dt
        self.ret = np.zeros(samples)
        self.ticks = np.zeros(samples, int)
        self.finished: list[tuple[float, float]] = []

    def add(self, reward: np.ndarray, done: np.ndarray, active: np.ndarray):
        """An episode is one creature's life: the dead count nothing until their arena starts over."""
        self.ret += reward * active
        self.ticks += active
        done = done & active
        for i in np.flatnonzero(done):
            self.finished.append((float(self.ret[i]), float(self.ticks[i] * self.dt)))
        self.ret[done] = 0
        self.ticks[done] = 0

    def take(self) -> dict:
        done, self.finished = self.finished, []
        if not done:
            return {'episodes': 0}
        ret, seconds = np.array(done).T
        return {'episodes': len(done), 'episode_return': float(ret.mean()), 'episode_seconds': float(seconds.mean())}


def kept(notes: torch.Tensor, active: np.ndarray, done: np.ndarray) -> torch.Tensor:
    """Notes after a step: wiped for those that weren't alive to act (so a hatchling starts blank) and for those
    whose life ended."""
    return notes * torch.from_numpy(active & ~done).to(notes)[:, None]


def collect(env: Forage, actor: Brain, steps: int, obs: Observation, episodes: Episodes,
            notes: torch.Tensor) -> tuple[Rollout, Observation, torch.Tensor]:
    keep: dict[str, list] = {k: [] for k in Rollout.__dataclass_fields__ if k != 'notes'}
    start = notes.numpy()[None]
    with torch.no_grad():
        for _ in range(steps):
            mean, value, notes = actor(*tensors(obs, 'cpu'), notes)
            dist = actor.dist(mean)
            action = dist.sample()
            for k, v in (('me', obs.me), ('kinds', obs.kinds), ('rays', obs.rays)):
                keep[k].append(v)
            keep['actions'].append(action.numpy())
            keep['logprobs'].append(dist.log_prob(action).sum(-1).numpy())
            keep['values'].append(value.numpy())
            active = env.active
            keep['active'].append(active)
            keep['hints'].append(env.hint)
            obs, reward, done, _ = env.step(action.numpy())
            episodes.add(reward, done, active)
            if env.final is not None:
                # cut off by the time limit, not ended: what's left is worth what the value says it is
                _, after, _ = actor(*tensors(env.final, 'cpu'), notes)
                reward = reward + env.gamma * after.numpy() * env.cut
            notes = kept(notes, active, done)
            keep['rewards'].append(reward)
            keep['dones'].append(done)
    return Rollout(**{k: np.stack(v) for k, v in keep.items()}, notes=start), obs, notes


def advantages(rewards, values, dones, last_value, gamma: float, lam: float) -> tuple[np.ndarray, np.ndarray]:
    """GAE over (steps, samples). last_value is the value of the observation after the final step."""
    adv = np.zeros_like(rewards)
    running = np.zeros_like(last_value)
    for t in reversed(range(len(rewards))):
        going = 1.0 - dones[t]
        following = values[t + 1] if t + 1 < len(rewards) else last_value
        delta = rewards[t] + gamma * following * going - values[t]
        running = delta + gamma * lam * going * running
        adv[t] = running
    return adv, adv + values


class Side(nn.Module):
    """A side job for a brain with memory: from its notes, say what it made of the moment `back` choices ago. In a
    toy test the notes learned a 10 s wait only with this, since nothing else pays for holding the past until reading
    it already pays. Kept out of the brain and thrown away after training."""

    def __init__(self, memory: int, width: int, back: int):
        super().__init__()
        self.back = back
        self.guess = nn.Linear(memory, width)

    def loss(self, moments: torch.Tensor, notes: torch.Tensor, carry: torch.Tensor, active: torch.Tensor) -> torch.Tensor:
        """moments and notes (steps, n, ...); only pairs with no restart between them count."""
        k = self.back
        steps = len(moments)
        if k >= steps:
            return moments.new_zeros(())
        # breaks before each step: a stretch t-k..t is one stream when none fall inside it
        before = torch.cat([carry.new_zeros(1, carry.shape[1]), torch.cumsum(1 - carry, 0)])[:steps]
        whole = (before[k:] == before[:-k]) & active[k:] & active[:-k]
        if not whole.any():
            return moments.new_zeros(())
        err = ((self.guess(notes[k:].float()) - moments[:-k].detach().float()) ** 2).mean(-1)
        return err[whole].mean()


class Closure(nn.Module):
    """A side job for a brain with memory in a maze: from its notes, say whether it has been in this room before
    (loop closure, which helped agents learn mazes in Mirowski et al. 2016). Only memory can answer it, so it pays the
    notes for keeping where they've been. Like Side, kept out of the brain and thrown away after training."""

    def __init__(self, memory: int):
        super().__init__()
        self.guess = nn.Linear(memory, 1)

    def loss(self, notes: torch.Tensor, hints: torch.Tensor, active: torch.Tensor) -> tuple[torch.Tensor, float]:
        """notes and hints (steps, n, ...): the error over the living, and the share it gets right."""
        if not active.any():
            return notes.new_zeros(()), 0.0
        logit = self.guess(notes[active].float()).squeeze(-1)
        target = hints[active].float()
        right = ((logit > 0) == (target > 0.5)).float().mean().item()
        return nn.functional.binary_cross_entropy_with_logits(logit, target), right


def update(learner: Brain, optimizer: torch.optim.Optimizer, roll: Rollout, adv: np.ndarray, returns: np.ndarray,
           cfg: PPO, bf16: bool = False, side: Side | None = None, closure: Closure | None = None) -> dict:
    if learner.memory:
        return update_streams(learner, optimizer, roll, adv, returns, cfg, bf16, side, closure)
    device = next(learner.parameters()).device

    # only what living creatures did; the dead's samples are placeholders
    active = roll.active.reshape(-1)

    def flat(x: np.ndarray) -> torch.Tensor:
        return torch.from_numpy(np.ascontiguousarray(x.reshape(-1, *x.shape[2:])[active])).to(device)

    me, kinds, rays = flat(roll.me), flat(roll.kinds), flat(roll.rays)
    actions, old_logp = flat(roll.actions), flat(roll.logprobs)
    adv_t, ret_t = flat(adv.astype(np.float32)), flat(returns.astype(np.float32))
    n = len(me)
    size = n // cfg.minibatches
    seen: dict[str, list[float]] = {'policy_loss': [], 'value_loss': [], 'entropy': [], 'kl': [], 'clipped': []}
    for _ in range(cfg.epochs):
        order = torch.randperm(n, device=device)
        for start in range(0, size * cfg.minibatches, size):
            mb = order[start:start + size]
            # bf16 for the brain's own maths only; the losses stay float32
            with torch.autocast(device.type, torch.bfloat16, enabled=bf16):
                mean, value, _ = learner(me[mb], kinds[mb], rays[mb])
            step(learner, optimizer, cfg, seen, mean, value, actions[mb], old_logp[mb], adv_t[mb], ret_t[mb])
    return summed(learner, roll, returns, seen)


def update_streams(learner: Brain, optimizer: torch.optim.Optimizer, roll: Rollout, adv: np.ndarray,
                   returns: np.ndarray, cfg: PPO, bf16: bool = False, side: Side | None = None,
                   closure: Closure | None = None) -> dict:
    """update() for a brain with memory: minibatches of whole streams, each replayed in order from its starting
    notes, the notes kept or wiped as they were while collecting. Only living creatures' choices count."""
    device = next(learner.parameters()).device
    steps, streams = roll.active.shape

    def put(x: np.ndarray) -> torch.Tensor:
        return torch.from_numpy(np.ascontiguousarray(x)).to(device)

    me, kinds, rays = put(roll.me), put(roll.kinds), put(roll.rays)
    actions, old_logp = put(roll.actions), put(roll.logprobs)
    adv_t, ret_t = put(adv.astype(np.float32)), put(returns.astype(np.float32))
    active, start = put(roll.active), put(roll.notes[0])
    carry = put(roll.active & ~roll.dones).float()
    size = streams // cfg.minibatches
    seen: dict[str, list[float]] = {'policy_loss': [], 'value_loss': [], 'entropy': [], 'kl': [], 'clipped': []}
    if side:
        seen['side_loss'] = []
    if closure:
        # right against base: how often "been here" is the answer, which always saying the commoner one gets
        seen['closure_loss'], seen['closure_right'], seen['closure_base'] = [], [], []
    hints = put(roll.hints) if closure else None
    for _ in range(cfg.epochs):
        order = torch.randperm(streams, device=device)
        for first in range(0, size * cfg.minibatches, size):
            mb = order[first:first + size]
            extra = None
            with torch.autocast(device.type, torch.bfloat16, enabled=bf16):
                mean, value, kept = replay(learner, me[:, mb], kinds[:, mb], rays[:, mb], start[mb], carry[:, mb],
                                           keep=side is not None or closure is not None)
            if side:
                assert kept is not None
                lost = side.loss(kept[0], kept[1], carry[:, mb], active[:, mb])
                seen['side_loss'].append(lost.item())
                extra = cfg.side * lost
            if closure:
                assert kept is not None and hints is not None
                lost, right = closure.loss(kept[1], hints[:, mb], active[:, mb])
                seen['closure_loss'].append(lost.item())
                seen['closure_right'].append(right)
                seen['closure_base'].append(hints[:, mb][active[:, mb]].mean().item())
                extra = cfg.closure * lost + (extra if extra is not None else 0)
            live = active[:, mb].flatten()
            pick = lambda x: x[:, mb].flatten(0, 1)[live]
            step(learner, optimizer, cfg, seen, mean[live], value[live], pick(actions), pick(old_logp),
                 pick(adv_t), pick(ret_t), extra)
    return summed(learner, roll, returns, seen)


def replay(learner: Brain, me: torch.Tensor, kinds: torch.Tensor, rays: torch.Tensor, start: torch.Tensor,
           carry: torch.Tensor, keep: bool = False):
    """Streams (steps, n, ...) played again from their starting notes, kept where carry is 1: mean actions and
    values, (steps * n, ...), and with keep, the moments and the notes after each step, (steps, n, ...)."""
    steps, n = carry.shape
    # what each moment looks like doesn't depend on the notes, so that part runs for all steps at once
    moments = learner.sense(me.flatten(0, 1), kinds.flatten(0, 1), rays.flatten(0, 1)).view(steps, n, -1)
    outs, written = learner.remember_streams(moments, start, carry)
    mean, value = learner.heads(outs.flatten(0, 1))
    return mean, value, ((moments, written) if keep else None)


def step(learner: Brain, optimizer: torch.optim.Optimizer, cfg: PPO, seen: dict[str, list[float]],
         mean: torch.Tensor, value: torch.Tensor, actions: torch.Tensor, old_logp: torch.Tensor,
         adv: torch.Tensor, ret: torch.Tensor, extra: torch.Tensor | None = None):
    """One clipped PPO step on a minibatch, the losses in float32, plus any extra loss (a side job's)."""
    mean, value = mean.float(), value.float()
    dist = learner.dist(mean)
    log_ratio = dist.log_prob(actions).sum(-1) - old_logp
    ratio = log_ratio.exp()
    a = (adv - adv.mean()) / (adv.std() + 1e-8)
    policy_loss = torch.max(-a * ratio, -a * ratio.clamp(1 - cfg.clip, 1 + cfg.clip)).mean()
    value_loss = 0.5 * ((value - ret) ** 2).mean()
    entropy = dist.entropy().sum(-1).mean()
    loss = policy_loss - cfg.entropy * entropy + cfg.value * value_loss
    if cfg.coins:
        loss = loss - cfg.coins * dist.coin_entropy(learner.named(cfg.coins_for)).mean()
    if extra is not None:
        loss = loss + extra
    optimizer.zero_grad()
    loss.backward()
    nn.utils.clip_grad_norm_(learner.parameters(), cfg.max_grad_norm)
    optimizer.step()
    with torch.no_grad():
        seen['policy_loss'].append(policy_loss.item())
        seen['value_loss'].append(value_loss.item())
        seen['entropy'].append(entropy.item())
        seen['kl'].append(((ratio - 1) - log_ratio).mean().item())
        seen['clipped'].append(((ratio - 1).abs() > cfg.clip).float().mean().item())


def summed(learner: Brain, roll: Rollout, returns: np.ndarray, seen: dict[str, list[float]]) -> dict:
    stats: dict[str, float | list[float]] = {k: float(np.mean(v)) for k, v in seen.items()}
    returns, values = returns[roll.active], roll.values[roll.active]
    var = returns.var()
    stats['explained_variance'] = float(1 - (returns - values).var() / var) if var > 0 else 0.0
    stats['std'] = learner.log_std.exp().tolist()
    return stats
