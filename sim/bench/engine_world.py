# Candidate 2: pymunk (Chipmunk2D), one Space per arena. Creatures are circles
# pushed by a force each tick; blocks are real rigid boxes.
# Body state moves in and out through pymunk.batch so the per-body Python cost
# is as low as pymunk allows.

import numpy as np
import pymunk
import pymunk.batch

from rays import START
from scene import (BLOCK_START, BLOCKS, CREATURE_MASS, CREATURES, DT, FOOD, FOOD_RADIUS, GROUND_FRICTION, HALF,
                   RADIUS, RAY_RANGE, friction_torque, initial_state, steer)

CREATURE, BLOCK, WALL, FOOD_CAT = 1, 2, 4, 8
# floats per body for POSITION | ANGLE | VELOCITY | ANGULAR_VELOCITY
FIELDS = (pymunk.batch.BodyFields.POSITION | pymunk.batch.BodyFields.ANGLE
          | pymunk.batch.BodyFields.VELOCITY | pymunk.batch.BodyFields.ANGULAR_VELOCITY)
WIDTH = 6
# two substeps and 1 cm of allowed overlap keep creatures within a few cm of touching; see docs/physics.md
SUBSTEPS = 2
SLOP = 0.01


class EngineWorld:
    def __init__(self, arenas: int, seed: int = 0, food_shapes: bool = False):
        self.arenas = arenas
        pos, self.heading = initial_state(arenas, seed)
        self.vel = np.zeros_like(pos)
        self.spaces = [self._build(pos[a]) for a in range(arenas)]
        self.food_shapes = [self._add_food(s) for s in self.spaces] if food_shapes else None
        # batch rows are the dynamic bodies in the order added, then the space's static body
        self.rows = CREATURES + len(BLOCKS) + 1
        self.data = np.zeros((arenas, self.rows * WIDTH))
        self.force = np.zeros((arenas, self.rows * 2))
        # separate read and write buffers: a write buffer wraps our numpy memory, which pymunk mustn't grow
        self.reads = [pymunk.batch.Buffer() for _ in range(arenas)]
        self.writes = [pymunk.batch.Buffer() for _ in range(arenas)]
        self._read()

    def _build(self, creatures):
        space = pymunk.Space()
        space.collision_slop = SLOP
        for x, y in creatures:
            body = pymunk.Body(CREATURE_MASS, float('inf'))
            body.position = (x, y)
            shape = pymunk.Circle(body, RADIUS)
            shape.friction = 0.2
            shape.filter = pymunk.ShapeFilter(categories=CREATURE, mask=CREATURE | BLOCK | WALL)
            space.add(body, shape)
        for (w, h, m), (x, y) in zip(BLOCKS, BLOCK_START):
            body = pymunk.Body(m, pymunk.moment_for_box(m, (w, h)))
            body.position = (x, y)
            shape = pymunk.Poly.create_box(body, (w, h))
            shape.friction = 0.6
            shape.filter = pymunk.ShapeFilter(categories=BLOCK, mask=CREATURE | BLOCK | WALL)
            space.add(body, shape)
            # top-down ground friction: joints to the ground that resist up to a set force and torque
            slide = pymunk.PivotJoint(space.static_body, body, (0, 0), (0, 0))
            spin = pymunk.GearJoint(space.static_body, body, 0, 1)
            slide.max_bias = spin.max_bias = 0
            slide.max_force = m * GROUND_FRICTION
            spin.max_force = friction_torque(w, h, m)
            space.add(slide, spin)
        corners = [(-HALF, -HALF), (HALF, -HALF), (HALF, HALF), (-HALF, HALF)]
        for a, b in zip(corners, corners[1:] + corners[:1]):
            wall = pymunk.Segment(space.static_body, a, b, 0)
            wall.friction = 0.2
            wall.filter = pymunk.ShapeFilter(categories=WALL)
            space.add(wall)
        return space

    def _add_food(self, space):
        """Food as query-only circles on the static body, so native ray casts can see it."""
        shapes = []
        for _ in range(FOOD):
            shape = pymunk.Circle(space.static_body, FOOD_RADIUS)
            # a mask of only its own category: bodies reject it, queries (which match everything) don't
            shape.filter = pymunk.ShapeFilter(categories=FOOD_CAT, mask=FOOD_CAT)
            space.add(shape)
            shapes.append(shape)
        return shapes

    def _read(self):
        for a, space in enumerate(self.spaces):
            buf = self.reads[a]
            buf.clear()
            pymunk.batch.get_space_bodies(space, FIELDS, buf)
            self.data[a] = np.frombuffer(buf.float_buf())
        d = self.data.reshape(self.arenas, self.rows, WIDTH)
        self.vel = d[:, :CREATURES, 3:5].copy()
        self.pos = d[:, :CREATURES, 0:2].copy()
        self.bpos = d[:, CREATURES:-1, 0:2].copy()
        self.bang = d[:, CREATURES:-1, 2].copy()

    def step(self, actions: np.ndarray):
        # the force that gives steer()'s velocity change when nothing is in the way;
        # setting velocity directly would undo the solver's contact pushes every tick
        self.heading, vel = steer(self.heading, self.vel, actions)
        f = self.force.reshape(self.arenas, self.rows, 2)
        f[:, :CREATURES] = (vel - self.vel) * (CREATURE_MASS / DT)
        for a, space in enumerate(self.spaces):
            buf = self.writes[a]
            buf.set_float_buf(self.force[a])
            # pymunk clears forces after every step
            for _ in range(SUBSTEPS):
                pymunk.batch.set_space_bodies(space, pymunk.batch.BodyFields.FORCE, buf)
                space.step(DT / SUBSTEPS)
        self._read()

    def sync_food(self, food_pos, moved):
        for a, i in zip(*np.nonzero(moved)):
            shape = self.food_shapes[a][i]
            shape.unsafe_set_offset((float(food_pos[a, i, 0]), float(food_pos[a, i, 1])))
            self.spaces[a].reindex_shape(shape)

    def cast_rays(self, dirs: np.ndarray):
        """pymunk's own segment queries, one Python call per ray. dirs is (arenas, creatures, rays, 2)."""
        out = np.full(dirs.shape[:3], RAY_RANGE)
        for a, space in enumerate(self.spaces):
            for i in range(CREATURES):
                ox, oy = self.pos[a, i]
                for r in range(dirs.shape[2]):
                    dx, dy = dirs[a, i, r]
                    start = (ox + dx * START, oy + dy * START)
                    end = (ox + dx * RAY_RANGE, oy + dy * RAY_RANGE)
                    hit = space.segment_query_first(start, end, 0, pymunk.ShapeFilter())
                    if hit is not None:
                        out[a, i, r] = START + hit.alpha * (RAY_RANGE - START)
        return out

    def state(self):
        return self.pos, self.heading, self.bpos, self.bang
