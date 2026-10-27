# PPO, shaped after CleanRL's continuous-action version: collect a rollout on
# the CPU, work out advantages with GAE, then a few clipped passes over it on
# the learner's device. Each creature in each arena is one sample stream.
#
# A brain with memory learns from whole streams instead of shuffled samples: each pass replays a stream's choices in
# order from the notes it had at the rollout's start, so what it learns to write down is paid for by what that does
# for its choices later in the rollout (backpropagation through time, as CleanRL's LSTM PPO does it).

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


def update(learner: Brain, optimizer: torch.optim.Optimizer, roll: Rollout, adv: np.ndarray, returns: np.ndarray,
           cfg: PPO, bf16: bool = False) -> dict:
    if learner.memory:
        return update_streams(learner, optimizer, roll, adv, returns, cfg, bf16)
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
                   returns: np.ndarray, cfg: PPO, bf16: bool = False) -> dict:
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
    for _ in range(cfg.epochs):
        order = torch.randperm(streams, device=device)
        for first in range(0, size * cfg.minibatches, size):
            mb = order[first:first + size]
            with torch.autocast(device.type, torch.bfloat16, enabled=bf16):
                mean, value = replay(learner, me[:, mb], kinds[:, mb], rays[:, mb], start[mb], carry[:, mb])
            live = active[:, mb].flatten()
            pick = lambda x: x[:, mb].flatten(0, 1)[live]
            step(learner, optimizer, cfg, seen, mean[live], value[live], pick(actions), pick(old_logp),
                 pick(adv_t), pick(ret_t))
    return summed(learner, roll, returns, seen)


def replay(learner: Brain, me: torch.Tensor, kinds: torch.Tensor, rays: torch.Tensor, start: torch.Tensor,
           carry: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """Streams (steps, n, ...) played again from their starting notes, kept where carry is 1: mean actions and
    values, (steps * n, ...)."""
    steps, n = carry.shape
    # what each moment looks like doesn't depend on the notes, so that part runs for all steps at once
    moments = learner.sense(me.flatten(0, 1), kinds.flatten(0, 1), rays.flatten(0, 1)).view(steps, n, -1)
    notes, outs = start, []
    for t in range(steps):
        out, notes = learner.remember(moments[t], notes)
        outs.append(out)
        notes = notes * carry[t, :, None]
    return learner.heads(torch.stack(outs).flatten(0, 1))


def step(learner: Brain, optimizer: torch.optim.Optimizer, cfg: PPO, seen: dict[str, list[float]],
         mean: torch.Tensor, value: torch.Tensor, actions: torch.Tensor, old_logp: torch.Tensor,
         adv: torch.Tensor, ret: torch.Tensor):
    """One clipped PPO step on a minibatch, the losses in float32."""
    mean, value = mean.float(), value.float()
    dist = learner.dist(mean)
    log_ratio = dist.log_prob(actions).sum(-1) - old_logp
    ratio = log_ratio.exp()
    a = (adv - adv.mean()) / (adv.std() + 1e-8)
    policy_loss = torch.max(-a * ratio, -a * ratio.clamp(1 - cfg.clip, 1 + cfg.clip)).mean()
    value_loss = 0.5 * ((value - ret) ** 2).mean()
    entropy = dist.entropy().sum(-1).mean()
    loss = policy_loss - cfg.entropy * entropy + cfg.value * value_loss
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
