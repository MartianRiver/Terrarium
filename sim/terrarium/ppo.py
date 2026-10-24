# PPO, shaped after CleanRL's continuous-action version: collect a rollout on
# the CPU, work out advantages with GAE, then a few clipped passes over it on
# the learner's device. Each creature in each arena is one sample stream.

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


def collect(env: Forage, actor: Brain, steps: int, obs: Observation, episodes: Episodes) -> tuple[Rollout, Observation]:
    keep: dict[str, list] = {k: [] for k in Rollout.__dataclass_fields__}
    with torch.no_grad():
        for _ in range(steps):
            mean, value = actor(*tensors(obs, 'cpu'))
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
            keep['rewards'].append(reward)
            keep['dones'].append(done)
            episodes.add(reward, done, active)
    return Rollout(**{k: np.stack(v) for k, v in keep.items()}), obs


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
           cfg: PPO) -> dict:
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
            mean, value = learner(me[mb], kinds[mb], rays[mb])
            dist = learner.dist(mean)
            log_ratio = dist.log_prob(actions[mb]).sum(-1) - old_logp[mb]
            ratio = log_ratio.exp()
            a = adv_t[mb]
            a = (a - a.mean()) / (a.std() + 1e-8)
            policy_loss = torch.max(-a * ratio, -a * ratio.clamp(1 - cfg.clip, 1 + cfg.clip)).mean()
            value_loss = 0.5 * ((value - ret_t[mb]) ** 2).mean()
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
    stats: dict[str, float | list[float]] = {k: float(np.mean(v)) for k, v in seen.items()}
    returns, values = returns[roll.active], roll.values[roll.active]
    var = returns.var()
    stats['explained_variance'] = float(1 - (returns - values).var() / var) if var > 0 else 0.0
    stats['std'] = learner.log_std.exp().tolist()
    return stats
