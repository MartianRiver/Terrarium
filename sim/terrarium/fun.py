# Fun ([reward] novelty and variety, in training only): what a Terrikin gets out of the world moving because of it
# (each metre a block moves while it's touching or holding it), and out of doing something it hasn't done lately
# (a yes to an action it rarely says yes to). Both wear off the more it's done, as boredom, and come back once it's
# been a while, so pushing the same block back and forth soon stops paying.

import numpy as np

from .world import World

# moving this many metres of blocks, or saying yes to an action for this many ticks, makes it half as much fun
BORED_METRES = 2.0
BORED_TICKS = 40
# and half of that is forgotten after this many seconds
FORGET = 60.0
# how close counts as touching a block, beyond the body, when grab doesn't say
TOUCH = 0.05


class Fun:
    def __init__(self, world: World, novelty: float, variety: float):
        self.world, self.novelty, self.variety = world, novelty, variety
        cfg = world.cfg
        self.half = np.array([(b.w / 2, b.h / 2) for b in cfg.block]).reshape(-1, 2)
        self.reach = cfg.creature.radius + max(cfg.grab.reach, TOUCH)
        self.blocks = world.block_pos.copy()
        self.moved = np.zeros(world.alive.shape)
        self.said = np.zeros(world.alive.shape + (4,))
        self.fade = 0.5 ** (cfg.dt / FORGET)
        self.was_lifted = self.world.blocks_carried

    def touching(self) -> np.ndarray:
        """Which blocks each creature is touching or close enough to hold, (arenas, creatures, blocks)."""
        w = self.world
        d = w.pos[:, :, None] - w.block_pos[:, None]
        cos, sin = np.cos(w.block_angle)[:, None], np.sin(w.block_angle)[:, None]
        x, y = d[..., 0] * cos + d[..., 1] * sin, -d[..., 0] * sin + d[..., 1] * cos
        gap = np.hypot(np.maximum(np.abs(x) - self.half[:, 0], 0), np.maximum(np.abs(y) - self.half[:, 1], 0))
        return gap < self.reach

    def step(self, actions: np.ndarray) -> np.ndarray:
        """After a world tick: each creature's fun from it, (arenas, creatures). actions as the world took them."""
        w = self.world
        out = np.zeros(w.alive.shape)
        if len(self.half):
            # a block carried off the ground waits far outside the arena, so the ticks it's lifted and set down
            # aren't moves
            lifted = w.blocks_carried
            shifted = np.hypot(*(w.block_pos - self.blocks).transpose(2, 0, 1)) * ~(lifted | self.was_lifted)
            self.was_lifted = lifted
            mine = (self.touching() * shifted[:, None]).sum(-1) * w.alive
            out += self.novelty * mine * 0.5 ** (self.moved / BORED_METRES)
            self.moved += mine
            self.blocks = w.block_pos.copy()
        # unload, eat, sprint and grab, as many as the actions have
        yes = np.zeros(self.said.shape)
        k = min(actions.shape[-1] - 2, 4)
        yes[..., :k] = (actions[..., 2:2 + k] > 0) & w.alive[..., None]
        out += self.variety * (yes * 0.5 ** (self.said / BORED_TICKS)).sum(-1)
        self.said += yes
        self.moved *= self.fade
        self.said *= self.fade
        return out

    def reset(self, arenas: np.ndarray):
        self.moved[arenas] = 0
        self.said[arenas] = 0
        self.blocks[arenas] = self.world.block_pos[arenas]
        self.was_lifted[arenas] = self.world.blocks_carried[arenas]
