# A wider brain that starts out acting as a narrower one does (Net2WiderNet, Chen et al. 2016).
#
#   uv run python -m terrarium.widen IN.pt OUT.pt --width 128 [--noise 0.01]
#
# Every unit is copied k = width / old width times and whatever reads the copies gets 1/k of the weight from each,
# so each layer computes the same as before. Copying, not zero-padding, because a layer norm over the wider stream
# then sees the same mean and spread. Heads are copied too, so each head stays as wide as it was. Copies get the
# same gradients and would stay copies for good, so a little noise (a share of each weight's own spread) parts them.
import argparse

import torch

from .brain import Brain, load, save


def widen(old: Brain, width: int, noise: float = 0.0, seed: int = 0) -> Brain:
    w, k = old.shape['width'], width // old.shape['width']
    if width % w or k < 2:
        raise ValueError(f'width {width} has to be a multiple of {w}, at least twice it')
    new = Brain(width, old.shape['layers'], old.shape['heads'] * k, old.schema)
    state = new.state_dict()

    def rows(t):
        # an output the stream carries: k copies along the first axis
        return t.repeat(k, *[1] * (t.dim() - 1))

    def cols(t):
        # an input from the stream: k copies along the last axis, each with 1/k of the weight
        return t.repeat(*[1] * (t.dim() - 1), k) / k

    for name, t in old.state_dict().items():
        if name.startswith(('policy.', 'value.', 'log_std')):
            # the heads read the stream and write actions and the value, which don't widen
            out = cols(t) if name.endswith('weight') else t
        elif name == 'kind.weight':
            out = t.repeat(1, k)
        elif name.endswith('in_proj_weight'):
            # queries, keys and values stacked; copying each one's rows copies its heads
            out = torch.cat([rows(cols(q)) for q in t.chunk(3)])
        elif name.endswith('in_proj_bias'):
            out = torch.cat([rows(q) for q in t.chunk(3)])
        elif t.dim() == 2 and not name.startswith(('me.', 'ray.')):
            out = rows(cols(t))
        else:
            # the senses' maps, biases and norms: what they write is copied
            out = rows(t)
        state[name] = out
    if noise:
        g = torch.Generator().manual_seed(seed)
        for t in state.values():
            if t.dim() == 2:
                t += torch.randn(t.shape, generator=g) * noise * t.std()
    new.load_state_dict(state)
    return new


def main():
    parser = argparse.ArgumentParser(description='Write a wider copy of a brain that starts out acting the same.')
    parser.add_argument('brain')
    parser.add_argument('out')
    parser.add_argument('--width', type=int, required=True)
    parser.add_argument('--noise', type=float, default=0.01, help="share of each weight matrix's spread added as noise")
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    old, meta = load(args.brain)
    new = widen(old, args.width, args.noise, args.seed)
    print(save(new, args.out, **meta, widened_from=old.shape['width']))


if __name__ == '__main__':
    main()
