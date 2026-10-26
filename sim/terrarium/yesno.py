# A brain's yes/no actions (unload, eat, sprint, grab) as coins instead of a
# Gaussian cut at 0, with about the odds they had, so it acts the same at the
# start (brain.py, to_bernoulli). A coin trains its odds directly; the cut
# Gaussian can push its mean so far below 0 that yes stops being tried.
#
#   uv run python -m terrarium.yesno IN.pt OUT.pt

import argparse

from .brain import brain_id, load, save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('brain')
    parser.add_argument('out')
    args = parser.parse_args()
    brain, meta = load(args.brain)
    if brain.yes_no == 'bernoulli':
        raise SystemExit(f'{args.brain} already tosses coins')
    brain.to_bernoulli()
    print(save(brain, args.out, **meta, coins_from=brain_id(args.brain)))


if __name__ == '__main__':
    main()
