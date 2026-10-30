# The brain: attention over a self token and one token per ray, each ray
# token being what it hit (an embedding per kind) plus where (a linear map of
# its features). The self token's output drives the policy and the value
# estimate. Steering is a Gaussian. A yes/no action is either a Gaussian too,
# yes when the draw is above 0 (how every brain began), or a coin with its own
# odds (Bernoulli): `yes_no` says which, and either way the world gets +1 for
# yes and -1 for no. Every creature runs a copy of the same brain.
#
# A brain can have memory: notes it carries from one choice to the next (a GRU, Cho et al. 2014), written from
# the self token's output and read back into it through a link that starts at zero, so a brain given memory acts
# exactly as it did without until training finds a use for the notes. Each creature's notes start blank when its
# life does (a new episode, or a hatchling in its place) and are wiped when it dies.
#
# Checkpoints carry their schema and are refused when it doesn't fit (schema.py).
# A brain from shorter lists loads with every new weight zero, which is what
# makes the lists safe to grow; new actions start as a fresh brain's do.

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
    memory: int


SHAPE: Shape = {'width': 64, 'layers': 2, 'heads': 4, 'memory': 0}
# a new action's spread, and where a yes/no one's mean starts: with that spread it's yes on about 5% of samples
LOG_STD = -0.5
NO = -1.0
# the same 5% as a coin's odds, log(0.05 / 0.95)
NO_ODDS = -2.944
# Φ(z) ≈ sigmoid(1.702 z), to turn a Gaussian yes/no into a coin with about the same odds
PROBIT = 1.702
YES_NO = ('gaussian', 'bernoulli')


class Actions:
    """The action distribution: per-action log_prob and entropy, as torch.distributions.Normal gives them."""

    def __init__(self, mean: torch.Tensor, log_std: torch.Tensor, coins: torch.Tensor | None):
        self.normal = torch.distributions.Normal(mean, log_std.exp().expand_as(mean))
        self.coins = coins
        if coins is not None:
            self.coin = torch.distributions.Bernoulli(logits=mean)

    def sample(self) -> torch.Tensor:
        action = self.normal.sample()
        if self.coins is not None:
            action = torch.where(self.coins, self.coin.sample() * 2 - 1, action)
        return action

    def log_prob(self, action: torch.Tensor) -> torch.Tensor:
        logp = self.normal.log_prob(action)
        if self.coins is not None:
            logp = torch.where(self.coins, self.coin.log_prob((action > 0).to(action.dtype)), logp)
        return logp

    def entropy(self) -> torch.Tensor:
        h = self.normal.entropy()
        return torch.where(self.coins, self.coin.entropy(), h) if self.coins is not None else h

    def coin_entropy(self, only: torch.Tensor | None = None) -> torch.Tensor:
        """Entropy of the coins alone (or of those in only), summed over them (zero for a brain without coins)."""
        if self.coins is None:
            return torch.zeros(self.normal.mean.shape[:-1], device=self.normal.mean.device)
        which = self.coins if only is None else self.coins & only
        return torch.where(which, self.coin.entropy(), 0.0).sum(-1)


class Brain(nn.Module):
    def __init__(self, width: int, layers: int, heads: int, lists: dict | None = None, yes_no: str = 'gaussian',
                 memory: int = 0):
        super().__init__()
        if yes_no not in YES_NO:
            raise ValueError(f'yes_no is one of {YES_NO}, not {yes_no!r}')
        self.schema = lists or schema.current()
        self.yes_no = yes_no
        self.shape: Shape = {'width': width, 'layers': layers, 'heads': heads, 'memory': memory}
        self.memory = memory
        s = self.schema
        self.me = nn.Linear(len(s['self']), width)
        self.ray = nn.Linear(len(s['ray']), width)
        self.kind = nn.Embedding(len(s['kinds']), width)
        layer = nn.TransformerEncoderLayer(width, heads, 2 * width, dropout=0.0, batch_first=True, norm_first=True)
        self.encoder = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        self.norm = nn.LayerNorm(width)
        self.policy = nn.Linear(width, len(s['actions']))
        self.log_std = nn.Parameter(torch.full((len(s['actions']),), LOG_STD))
        self.value = nn.Linear(width, 1)
        if memory:
            self.gru = nn.GRUCell(width, memory)
            self.recall = nn.Linear(memory, width)
            nn.init.zeros_(self.recall.weight)
            nn.init.zeros_(self.recall.bias)
        # small first actions, so training starts from gentle wandering rather than saturated turns
        nn.init.normal_(self.policy.weight, std=0.01)
        nn.init.zeros_(self.policy.bias)
        self.start_actions(0)

    def start_actions(self, first: int):
        """Set actions from index first on as a fresh brain has them."""
        with torch.no_grad():
            for i, name in enumerate(self.schema['actions'][first:], first):
                self.log_std[i] = LOG_STD
                self.policy.bias[i] = self.no() if name in schema.YES_NO else 0.0

    def restart(self, names: tuple[str, ...]):
        """Start these actions over as new ones start: nothing it sees moves them yet."""
        actions = self.schema['actions']
        if unknown := sorted(set(names) - set(actions)):
            raise ValueError(f'no such action: {", ".join(unknown)}')
        with torch.no_grad():
            for name in names:
                i = actions.index(name)
                self.policy.weight[i] = 0
                self.log_std[i] = LOG_STD
                self.policy.bias[i] = self.no() if name in schema.YES_NO else 0.0

    def no(self) -> float:
        return NO_ODDS if self.yes_no == 'bernoulli' else NO

    def coins(self) -> torch.Tensor | None:
        """Which actions are coins, or None if none are."""
        if self.yes_no != 'bernoulli':
            return None
        return torch.tensor([a in schema.YES_NO for a in self.schema['actions']], device=self.log_std.device)

    def named(self, names: tuple[str, ...]) -> torch.Tensor | None:
        """Which actions are these, or None (all of them) when names is empty."""
        if not names:
            return None
        if unknown := sorted(set(names) - set(self.schema['actions'])):
            raise ValueError(f'no such action: {", ".join(unknown)}')
        return torch.tensor([a in names for a in self.schema['actions']], device=self.log_std.device)

    def to_bernoulli(self):
        """Gaussian yes/no actions as coins with about the odds they had: a draw above 0 is Φ(mean / spread),
        close to a coin with odds 1.702 * mean / spread."""
        if self.yes_no == 'bernoulli':
            return
        with torch.no_grad():
            for i, name in enumerate(self.schema['actions']):
                if name in schema.YES_NO:
                    scale = PROBIT / self.log_std[i].exp()
                    self.policy.weight[i] *= scale
                    self.policy.bias[i] *= scale
        self.yes_no = 'bernoulli'

    def with_memory(self, size: int, recall: float = 0.0) -> 'Brain':
        """This brain with blank memory of `size` notes added; it acts exactly as before until it's trained, unless
        `recall` starts reading the notes back at that share of a fresh layer's weights."""
        if self.memory:
            raise ValueError(f'this brain already has memory ({self.memory} notes)')
        shape = self.shape
        new = Brain(shape['width'], shape['layers'], shape['heads'], self.schema, self.yes_no, size)
        missing, unexpected = new.load_state_dict(self.state_dict(), strict=False)
        assert not unexpected and all(k.startswith(('gru.', 'recall.')) for k in missing)
        if recall:
            # at zero the notes get no gradient until reading them pays, which at a few seconds' wait it rarely does
            with torch.no_grad():
                new.recall.weight.copy_(nn.Linear(size, shape['width']).weight * recall)
        return new.to(self.log_std.device)

    def blank(self, n: int) -> torch.Tensor:
        """Notes for n creatures that remember nothing yet ((n, 0) for a brain without memory)."""
        return torch.zeros(n, self.memory, device=self.log_std.device)

    def sense(self, me: torch.Tensor, kinds: torch.Tensor, rays: torch.Tensor) -> torch.Tensor:
        """What the self token makes of this moment, per sample."""
        tokens = torch.cat([self.me(me)[:, None], self.kind(kinds) + self.ray(rays)], 1)
        return self.norm(self.encoder(tokens)[:, 0])

    def remember(self, out: torch.Tensor, notes: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Write this moment into the notes, and read them back into what the heads see."""
        if not self.memory:
            return out, notes
        notes = self.gru(out, notes)
        return out + self.recall(notes), notes

    def remember_streams(self, moments: torch.Tensor, start: torch.Tensor, carry: torch.Tensor,
                         live: torch.Tensor | None = None) -> tuple[torch.Tensor, torch.Tensor]:
        """remember() over whole streams (steps, n, width) from their starting notes, wiped after each step where
        carry is 0: what the heads see and the notes after each step, (steps, n, ...). A tick at a time is a few
        small GPU calls a tick, which made the update most of a memory run's time, so each stream is cut at its
        wipes into pieces that start from blank notes and every piece goes through one GRU call. Steps that aren't
        live (the dead and the unborn) are left out and get blank notes, since nothing reads them."""
        steps, n = carry.shape
        if not self.memory:
            return moments, moments.new_zeros(steps, n, 0)
        live = carry.new_ones(steps, n, dtype=torch.bool) if live is None else live.bool()
        notes = moments.new_zeros(steps, n, self.memory, dtype=torch.float32)
        if live.any():
            # a piece starts at the first step and after each wipe; one starting at a step that isn't live would
            # hold only that step, padded to the longest piece (in colony-young, 44 times the pieces needed)
            begins = torch.cat([live.new_ones(1, n), carry[:-1] == 0]) & live
            count = begins.sum(0)
            piece = (torch.cumsum(count, 0) - count)[None] + torch.cumsum(begins.long(), 0) - 1
            t = torch.arange(steps, device=carry.device)[:, None].expand(steps, n)
            began = t.new_zeros(int(count.sum()))
            began[piece[begins]] = t[begins]
            which = piece[live]
            at = t[live] - began[which]
            g = self.gru
            with torch.autocast(moments.device.type, enabled=False):
                x = moments.new_zeros(int(at.max()) + 1, len(began), moments.shape[-1], dtype=torch.float32)
                x[at, which] = moments[live].float()
                h = moments.new_zeros(1, len(began), self.memory, dtype=torch.float32)
                h[0, piece[0][begins[0]]] = start[begins[0]].float()
                # what nn.GRU runs, with the GRUCell's own weights (same layout), so the brain's weights don't change
                out, _ = torch._VF.gru(x, h, [g.weight_ih, g.weight_hh, g.bias_ih, g.bias_hh],
                                       True, 1, 0.0, self.training, False, False)
                notes[live] = out[at, which]
        return moments + self.recall(notes).to(moments.dtype), notes

    def heads(self, out: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        return self.policy(out), self.value(out).squeeze(-1)

    def forward(self, me: torch.Tensor, kinds: torch.Tensor, rays: torch.Tensor,
                notes: torch.Tensor | None = None) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Mean action, value and the notes after this choice, per sample. Notes left out are blank."""
        out, notes = self.remember(self.sense(me, kinds, rays), self.blank(len(me)) if notes is None else notes)
        return *self.heads(out), notes

    def dist(self, mean: torch.Tensor) -> Actions:
        return Actions(mean, self.log_std, self.coins())

    def act(self, obs: Observation, sample: bool = True,
            notes: torch.Tensor | None = None) -> tuple[np.ndarray, torch.Tensor]:
        """Actions for a batch of observations, on the CPU, without gradients, and the notes after: for evals. Not
        sampled, it's the mean, which for a coin is its odds (yes when above 0)."""
        with torch.no_grad():
            mean, _, after = self(*tensors(obs, self.log_std.device), notes)
            action = self.dist(mean).sample() if sample else mean
        return action.cpu().numpy(), after


def tensors(obs: Observation, device) -> tuple[torch.Tensor, ...]:
    return tuple(torch.from_numpy(x).to(device) for x in (obs.me, obs.kinds, obs.rays))


def save(brain: Brain, path: Path | str, **meta) -> str:
    """Write a checkpoint and return its id, the sha256 of the file."""
    weights = {k: v.detach().cpu() for k, v in brain.state_dict().items()}
    torch.save({'format': FORMAT, 'schema': brain.schema, 'shape': brain.shape, 'yes_no': brain.yes_no,
                'weights': weights, 'meta': meta}, path)
    return brain_id(path)


def load(path: Path | str) -> tuple[Brain, dict]:
    """A checkpoint as a brain for today's schema, and the meta it was saved with."""
    data = torch.load(path, weights_only=True)
    if not isinstance(data, dict) or data.get('format') != FORMAT:
        raise schema.SchemaError(f'{path} isn\'t a Terrarium brain')
    schema.check(data['schema'])
    # brains from before memory have no 'memory' in their shape
    brain = Brain(**{'memory': 0, **data['shape']}, yes_no=data.get('yes_no', 'gaussian'))
    state = brain.state_dict()
    for name, old in data['weights'].items():
        # anything the lists have gained since is the zeros past the end of the saved tensor
        grown = torch.zeros_like(state[name]) if old.shape != state[name].shape else state[name]
        grown[tuple(slice(0, n) for n in old.shape)] = old
        state[name] = grown
    brain.load_state_dict(state)
    brain.start_actions(len(data['schema']['actions']))
    log.info('brain loaded', path=str(path), id=brain_id(path)[:12], schema=data['schema']['version'])
    return brain, data['meta']


def brain_id(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
