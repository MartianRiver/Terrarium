# Where a rollout's seconds go, summed by whichever process steps the worlds and runs the brain. Taken once a round
# (rollouts.py) and put in the metrics row (train.py). Plain accumulators: two perf_counter calls a region.

import time

now = time.perf_counter
KEYS = ('rays', 'rules', 'physics', 'brain')
spent: dict[str, float] = dict.fromkeys(KEYS, 0.0)


def take() -> dict[str, float]:
    out = dict(spent)
    for k in spent:
        spent[k] = 0.0
    return out


def combine(parts: list[dict[str, float]], parallel: bool) -> dict[str, float]:
    """Shares in worker processes play side by side, so a round's wall time is a share's, the mean; shares in this
    process play one after another, so it's their sum."""
    n = len(parts) if parallel else 1
    return {k: sum(p[k] for p in parts) / n for k in KEYS}
