# The brain: attention over a self token and one token per ray, each ray
# token being what it hit (an embedding per kind) plus where (a linear map of
# its features). The self token's output drives the policy (a Gaussian over the
# actions) and the value estimate. One brain acts for every creature.
#
# Checkpoints carry their schema and are refused when it doesn't fit (schema.py).
# A brain from shorter lists loads with every new weight zero, which is what
# makes the lists safe to grow.

import hashlib
from pathlib import Path
from typing import TypedDict

import numpy as np
import torch
from torch import nn

from . import schema
from .forage import Observation
from .log import Logger

log = Logger('brain')

FORMAT = 'terrarium-brain'


class Shape(TypedDict):
    width: int
    layers: int
    heads: int


SHAPE: Shape = {'width': 64, 'layers': 2, 'heads': 4}


class Brain(nn.Module):
    def __init__(self, width: int, layers: int, heads: int, lists: dict | None = None):
        super().__init__()
        self.schema = lists or schema.current()
        self.shape: Shape = {'width': width, 'layers': layers, 'heads': heads}
        s = self.schema
        self.me = nn.Linear(len(s['self']), width)
        self.ray = nn.Linear(len(s['ray']), width)
        self.kind = nn.Embedding(len(s['kinds']), width)
        layer = nn.TransformerEncoderLayer(width, heads, 2 * width, dropout=0.0, batch_first=True, norm_first=True)
        self.encoder = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        self.norm = nn.LayerNorm(width)
        self.policy = nn.Linear(width, len(s['actions']))
        self.log_std = nn.Parameter(torch.full((len(s['actions']),), -0.5))
        self.value = nn.Linear(width, 1)
        # small first actions, so training starts from gentle wandering rather than saturated turns
        nn.init.normal_(self.policy.weight, std=0.01)
        nn.init.zeros_(self.policy.bias)

    def forward(self, me: torch.Tensor, kinds: torch.Tensor, rays: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Mean action and value per sample."""
        tokens = torch.cat([self.me(me)[:, None], self.kind(kinds) + self.ray(rays)], 1)
        out = self.norm(self.encoder(tokens)[:, 0])
        return self.policy(out), self.value(out).squeeze(-1)

    def dist(self, mean: torch.Tensor) -> torch.distributions.Normal:
        return torch.distributions.Normal(mean, self.log_std.exp().expand_as(mean))

    def act(self, obs: Observation, sample: bool = True) -> np.ndarray:
        """Actions for a batch of observations, on the CPU, without gradients: for rollouts and evals."""
        with torch.no_grad():
            mean, _ = self(*tensors(obs, next(self.parameters()).device))
            action = self.dist(mean).sample() if sample else mean
        return action.cpu().numpy()


def tensors(obs: Observation, device) -> tuple[torch.Tensor, ...]:
    return tuple(torch.from_numpy(x).to(device) for x in (obs.me, obs.kinds, obs.rays))


def save(brain: Brain, path: Path | str, **meta) -> str:
    """Write a checkpoint and return its id, the sha256 of the file."""
    weights = {k: v.detach().cpu() for k, v in brain.state_dict().items()}
    torch.save({'format': FORMAT, 'schema': brain.schema, 'shape': brain.shape, 'weights': weights, 'meta': meta}, path)
    return brain_id(path)


def load(path: Path | str) -> tuple[Brain, dict]:
    """A checkpoint as a brain for today's schema, and the meta it was saved with."""
    data = torch.load(path, weights_only=True)
    if not isinstance(data, dict) or data.get('format') != FORMAT:
        raise schema.SchemaError(f'{path} isn\'t a Terrarium brain')
    schema.check(data['schema'])
    brain = Brain(**data['shape'])
    state = brain.state_dict()
    for name, old in data['weights'].items():
        # anything the lists have gained since is the zeros past the end of the saved tensor
        grown = torch.zeros_like(state[name]) if old.shape != state[name].shape else state[name]
        grown[tuple(slice(0, n) for n in old.shape)] = old
        state[name] = grown
    brain.load_state_dict(state)
    log.info('brain loaded', path=str(path), id=brain_id(path)[:12], schema=data['schema']['version'])
    return brain, data['meta']


def brain_id(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
