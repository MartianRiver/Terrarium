import numpy as np


class RandomActions:
    """Each creature holds a random (thrust, turn) for a spell, then picks again. Stands in for a brain."""

    def __init__(self, arenas: int, creatures: int, seed: int = 0, switch: float = 0.05):
        self.rng = np.random.default_rng(seed)
        self.switch = switch
        self.current = self._draw((arenas, creatures))

    def _draw(self, shape):
        thrust = self.rng.uniform(-0.3, 1.0, shape)
        turn = self.rng.uniform(-1.0, 1.0, shape)
        return np.stack([thrust, turn], -1)

    def __call__(self) -> np.ndarray:
        shape = self.current.shape[:2]
        change = self.rng.random(shape) < self.switch
        self.current = np.where(change[..., None], self._draw(shape), self.current)
        return self.current
