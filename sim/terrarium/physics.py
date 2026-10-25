# Bodies and contacts, on pymunk: one Space per arena. Creatures are circles
# pushed by a force; blocks are rigid boxes held back by ground friction.
# Everything else (energy, food, nests) is game logic in world.py.

import numpy as np
import pymunk
import pymunk.batch
from pymunk.constraints import GearJoint, PivotJoint

from .config import Config

CREATURE, BLOCK, WALL = 1, 2, 4
BLOCKS = pymunk.ShapeFilter(mask=BLOCK)
SOLID = pymunk.ShapeFilter(categories=CREATURE)
# a dead creature's body touches nothing, so nothing bumps into what's drawn as a tombstone
GONE = pymunk.ShapeFilter(categories=CREATURE, mask=0)
# walls are thick and sit outside the arena, so nothing squeezed against one can pop through it
WALL_THICKNESS = 0.5
# per body: position x, y, angle, velocity x, y, angular velocity
READ = (pymunk.batch.BodyFields.POSITION | pymunk.batch.BodyFields.ANGLE
        | pymunk.batch.BodyFields.VELOCITY | pymunk.batch.BodyFields.ANGULAR_VELOCITY)
WIDTH = 6


def friction_torque(cfg: Config, w, h, m):
    # average lever arm of the ground under a spinning box, roughly a third of its diagonal
    return m * cfg.ground.friction * np.hypot(w, h) / 3


class Physics:
    def __init__(self, cfg: Config, creatures: np.ndarray):
        self.cfg = cfg
        self.arenas, self.creatures = creatures.shape[:2]
        self.bodies: list[list[pymunk.Body]] = []
        self.spaces = [self._build(creatures[a]) for a in range(self.arenas)]
        # batch rows are the dynamic bodies in the order added, then the space's static body
        self.rows = self.creatures + len(cfg.block) + 1
        self.data = np.zeros((self.arenas, self.rows * WIDTH))
        self.force = np.zeros((self.arenas, self.rows * 2))
        # separate read and write buffers: a write buffer wraps numpy memory, which pymunk mustn't grow
        self.reads = [pymunk.batch.Buffer() for _ in range(self.arenas)]
        # (arena, creature) -> the joint it holds a block by
        self.held: dict[tuple[int, int], PivotJoint] = {}
        # and which block that is
        self.held_block: dict[tuple[int, int], int] = {}
        self.writes = [pymunk.batch.Buffer() for _ in range(self.arenas)]
        self.read()

    def _build(self, creatures):
        cfg = self.cfg
        space = pymunk.Space()
        space.collision_slop = cfg.slop
        bodies = []
        self.bodies.append(bodies)
        for x, y in creatures:
            body = pymunk.Body(cfg.creature.mass, float('inf'))
            body.position = (float(x), float(y))
            shape = pymunk.Circle(body, cfg.creature.radius)
            shape.friction = cfg.creature.friction
            shape.filter = SOLID
            space.add(body, shape)
            bodies.append(body)
        for b in cfg.block:
            body = pymunk.Body(b.mass, pymunk.moment_for_box(b.mass, (b.w, b.h)))
            body.position = (b.x, b.y)
            body.angle = b.angle
            shape = pymunk.Poly.create_box(body, (b.w, b.h))
            shape.friction = b.friction
            shape.filter = pymunk.ShapeFilter(categories=BLOCK)
            space.add(body, shape)
            bodies.append(body)
            # top-down ground friction: joints to the ground that resist up to a set force and torque
            slide = PivotJoint(space.static_body, body, (0, 0), (0, 0))
            spin = GearJoint(space.static_body, body, 0, 1)
            slide.max_bias = spin.max_bias = 0
            slide.max_force = b.mass * cfg.ground.friction
            spin.max_force = friction_torque(cfg, b.w, b.h, b.mass)
            space.add(slide, spin)
            if b.hinge:
                space.add(PivotJoint(space.static_body, body, body.local_to_world(b.hinge), b.hinge))
        r = WALL_THICKNESS / 2
        out = cfg.arena.size / 2 + r
        corners = [(-out, -out), (out, -out), (out, out), (-out, out)]
        for a, b in zip(corners, corners[1:] + corners[:1]):
            wall = pymunk.Segment(space.static_body, a, b, r)
            wall.friction = cfg.creature.friction
            wall.filter = pymunk.ShapeFilter(categories=WALL)
            space.add(wall)
        return space

    def read(self):
        for a, space in enumerate(self.spaces):
            buf = self.reads[a]
            buf.clear()
            pymunk.batch.get_space_bodies(space, READ, buf)
            self.data[a] = np.frombuffer(buf.float_buf())
        d = self.data.reshape(self.arenas, self.rows, WIDTH)
        n = self.creatures
        self.pos = d[:, :n, 0:2].copy()
        self.vel = d[:, :n, 3:5].copy()
        self.block_pos = d[:, n:-1, 0:2].copy()
        self.block_angle = d[:, n:-1, 2].copy()

    def grab(self, want: np.ndarray, reach: float, grip: float) -> np.ndarray:
        """Creatures that want to (arenas, creatures) take hold of the nearest block within reach of their edge, where it
        is, and keep hold until they don't want to; the rest let go. Returns who's holding one now."""
        for (a, c), joint in list(self.held.items()):
            if not want[a, c]:
                self.let_go(a, c)
        for a, c in zip(*np.nonzero(want)):
            if (a, c) in self.held:
                continue
            body = self.bodies[a][c]
            near = self.spaces[a].point_query_nearest(body.position, self.cfg.creature.radius + reach, BLOCKS)
            if near is None:
                continue
            block = near.shape.body
            # held at the point touched, as far off as it was: a creature at arm's length stays there
            joint = PivotJoint(body, block, near.point - body.position, block.world_to_local(near.point))
            joint.max_force = grip
            self.spaces[a].add(joint)
            self.held[int(a), int(c)] = joint
            self.held_block[int(a), int(c)] = self.bodies[a].index(block) - self.creatures
        holding = np.zeros(want.shape, bool)
        for a, c in self.held:
            holding[a, c] = True
        return holding

    def near_block(self, reach: float) -> np.ndarray:
        r = self.cfg.creature.radius + reach
        return np.array([[space.point_query_nearest(body.position, r, BLOCKS) is not None for body in bodies[:self.creatures]]
                         for space, bodies in zip(self.spaces, self.bodies)])

    def shift(self, arenas, blocks: list[int], to: np.ndarray, angles: np.ndarray):
        """Put these blocks at to (len(blocks), 2) and angles in each of arenas, standing still."""
        for a in arenas:
            for k, (x, y), angle in zip(blocks, to, angles):
                body = self.bodies[a][self.creatures + k]
                body.position = (float(x), float(y))
                body.angle = float(angle)
                body.velocity = (0, 0)
                body.angular_velocity = 0
        self.read()

    def let_go(self, a, c):
        self.held_block.pop((int(a), int(c)), None)
        joint = self.held.pop((int(a), int(c)), None)
        if joint is not None:
            self.spaces[a].remove(joint)

    def place(self, arenas, creatures: np.ndarray):
        """Creatures to these positions (len(arenas), creatures, 2), standing still, and blocks back where they started."""
        for a, pos in zip(arenas, creatures):
            for c in range(self.creatures):
                self.let_go(a, c)
            bodies = self.bodies[a]
            for body, (x, y) in zip(bodies, pos):
                body.position = (float(x), float(y))
                body.velocity = (0, 0)
                for shape in body.shapes:
                    shape.filter = SOLID
            for body, b in zip(bodies[self.creatures:], self.cfg.block):
                body.position = (b.x, b.y)
                body.angle = b.angle
                body.velocity = (0, 0)
                body.angular_velocity = 0
        self.read()

    def remove(self, creatures: np.ndarray):
        """Take these (arenas, creatures) out of the world where they stand, until their arena is placed again."""
        for a, c in zip(*np.nonzero(creatures)):
            self.let_go(a, c)
            body = self.bodies[a][c]
            body.velocity = (0, 0)
            for shape in body.shapes:
                shape.filter = GONE
        self.read()

    def step(self, force: np.ndarray):
        """Push each creature with force (arenas, creatures, 2) for one tick."""
        f = self.force.reshape(self.arenas, self.rows, 2)
        f[:, :self.creatures] = force
        substeps = self.cfg.substeps
        dt = self.cfg.dt / substeps
        for a, space in enumerate(self.spaces):
            buf = self.writes[a]
            buf.set_float_buf(self.force[a])
            # pymunk clears forces after every step
            for _ in range(substeps):
                pymunk.batch.set_space_bodies(space, pymunk.batch.BodyFields.FORCE, buf)
                space.step(dt)
        self.read()
