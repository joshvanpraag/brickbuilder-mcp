"""Strength check: where would a built model break?

The model is a graph: parts joined by studs (each stud sitting in a receiver) and joints.
A "weak link" is a single connection (a bridge in that graph) that, if it broke, would let
a section fall off. For each one we estimate:

  load      the weight of the section that hangs on it, in 1x1-brick units (by volume)
  lever     how far that weight sits out from the connection, in studs (a long arm
            twists the connection: think of a tall thin tower or a long sideways limb)
  strength  how much the connection holds, in studs: each stud 1; joints by type
            (ball joint-8 1.5, towball 2, large ball 3, hinge 2, clip 1, pin 1.5,
            axle 2, hinge fingers 2, turntable 4)

  risk = load x max(1, lever) / strength
  except for weight resting straight on top of a stud connection, which presses it
  together: there only the lever counts (risk = load x lever / strength). Rotating joints
  (hinges, balls, turntables, clips, pins) are held by friction alone, so they keep the
  full formula even under weight from above.

A risk over ~20 is worth reinforcing, and single-stud links carrying more than a couple of
bricks are always reported. The numbers are rough: they rank weak spots, not predict
exactly when something snaps.
"""
from __future__ import annotations

import functools

import numpy as np

from . import geometry

JOINT_STRENGTH = {"ball": 1.5, "socket": 1.5, "towball": 2, "towball_socket": 2, "large_ball": 3,
                  "large_socket": 3, "hinge_base": 2, "hinge_top": 2, "swivel_base": 2, "swivel_top": 2,
                  "click_hinge_1": 2, "click_hinge_2": 2, "clip": 1, "bar": 1, "pin": 1.5, "pin_hole": 1.5,
                  "axle": 2, "axle_hole": 2, "finger_m": 2, "finger_f": 2, "turntable_base": 4,
                  "turntable_top": 4, "turntable2_base": 3, "turntable2_top": 3, "flat_turntable": 4,
                  "snapstud": 4}
RISK_LIMIT = 20.0


@functools.lru_cache(maxsize=4096)
def _volume(part: str) -> float:
    """Part volume in 1x1-brick units (a 1x1 brick is 20 x 24 x 20 LDU)."""
    pts = geometry.samples(part)
    ref = len(geometry.samples("3005")) or 1
    return len(pts) / ref


def _links(model) -> dict[tuple[int, int], dict]:
    """Every pair of joined parts: {'strength': studs-equivalent, 'points': [world points]}."""
    links: dict[tuple[int, int], dict] = {}
    holes: dict = {}
    from .model import _key
    for i, g in model._geom.items():
        for pos, d in g.receivers():
            holes.setdefault(_key(pos), []).append((i, d))
    for i, g in model._geom.items():
        for pos, d in g.studs():
            for j, rd in holes.get(_key(pos), ()):
                if j != i and float(np.dot(d, rd)) < -0.9:
                    e = links.setdefault(tuple(sorted((i, j))), {"strength": 0.0, "points": [], "joint": False})
                    e["strength"] += 1
                    e["points"].append(np.asarray(pos, float))
    js = [(i, jt) for i, g in model._geom.items() for jt in g.joints_full()]
    for a in range(len(js)):
        i, j1 = js[a]
        for b in range(a + 1, len(js)):
            j, j2 = js[b]
            if i != j and model._joints_mate(j1, j2):
                e = links.setdefault(tuple(sorted((i, j))), {"strength": 0.0, "points": [], "joint": False})
                e["strength"] += JOINT_STRENGTH.get(j1[0], 1.5)
                e["joint"] = True
                e["points"].append(np.asarray(j1[1], float))
    return links


def _bridges(nodes, adj) -> list[tuple[int, int]]:
    """Edges whose removal disconnects the graph (iterative Tarjan)."""
    index, low, out = {}, {}, []
    counter = 0
    for root in nodes:
        if root in index:
            continue
        stack = [(root, None, iter(adj[root]))]
        index[root] = low[root] = counter
        counter += 1
        while stack:
            v, parent, it = stack[-1]
            advanced = False
            for w in it:
                if w == parent:
                    continue
                if w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append((w, v, iter(adj[w])))
                    advanced = True
                    break
                low[v] = min(low[v], index[w])
            if not advanced:
                stack.pop()
                if parent is not None:
                    low[parent] = min(low[parent], low[v])
                    if low[v] > index[parent]:
                        out.append((parent, v))
    return out


def report(model, limit: int = 15) -> dict:
    """Weak links, worst first: [{'parts': (a, b), 'strength', 'load', 'lever', 'risk',
    'holding': [part ids that would fall]}], plus totals."""
    links = _links(model)
    adj = {i: set() for i in model.parts}
    for a, b in links:
        adj[a].add(b)
        adj[b].add(a)
    grounded = {i for i in model.parts if model.grounded(i)}
    centre = {i: (g.aabb()[0] + g.aabb()[1]) / 2 for i, g in model._geom.items()}
    weight = {i: _volume(model.parts[i].part) for i in model.parts}
    rows = []
    for a, b in _bridges(list(model.parts), adj):
        # the side away from the ground is the part that would fall
        seen, stack = {b}, [b]
        while stack:
            v = stack.pop()
            for w in adj[v]:
                if (v, w) in ((a, b), (b, a)) or w in seen:
                    continue
                seen.add(w)
                stack.append(w)
        side_b = seen
        side_a = set(model.parts) - side_b
        on_a, on_b = bool(side_a & grounded), bool(side_b & grounded)
        if on_a and on_b:
            continue                                     # both sides stand on the ground
        if on_a != on_b:
            falls = side_b if on_a else side_a           # the side off the ground falls
        else:
            falls = side_b if len(side_b) <= len(side_a) else side_a   # nothing grounded
        e = links[tuple(sorted((a, b)))]
        load = sum(weight[i] for i in falls)
        if load <= 0:
            continue
        com = sum(centre[i] * weight[i] for i in falls) / load
        joint = np.mean(e["points"], axis=0)
        horiz = np.array([com[0] - joint[0], 0.0, com[2] - joint[2]])
        lever = float(np.linalg.norm(horiz)) / 20
        resting = com[1] < joint[1] - 4 and not e["joint"]   # -Y is up: the weight sits on top
        risk = load * (lever if resting else max(1.0, lever)) / max(e["strength"], 0.5)
        rows.append({"parts": (a, b), "strength": e["strength"], "load": round(load, 1),
                     "lever": round(lever, 1), "risk": round(risk, 1), "holding": sorted(falls),
                     "joint": e["joint"], "resting": resting})
    rows.sort(key=lambda r: -r["risk"])
    weak = [r for r in rows if r["risk"] > RISK_LIMIT or (r["strength"] <= 1 and r["load"] > 2)]
    return {"links": len(links), "weak_links": len(rows), "flagged": weak[:limit], "all": rows}


def describe(model, rep: dict) -> str:
    lines = [f"{len(model.parts)} parts, {rep['links']} connections, {rep['weak_links']} single points "
             f"of failure (a section hangs on one connection)."]
    if not rep["flagged"]:
        lines.append(f"Nothing flagged: no weak link carries a risky load (risk under {RISK_LIMIT:g}, "
                     "and no single stud holds more than 2 bricks' worth).")
        return "\n".join(lines)
    lines.append("Weak spots, worst first (load in 1x1-brick units, lever in studs, strength in studs):")
    for r in rep["flagged"]:
        a, b = r["parts"]
        pa, pb = model.parts[a].part, model.parts[b].part
        n = len(r["holding"])
        how = "rotating joint" if r["joint"] else ("resting on it" if r["resting"] else "hanging from it")
        lines.append(f"- #{a} {pa} <-> #{b} {pb} ({how}): strength {r['strength']:g}, holds {n} part"
                     f"{'s' if n != 1 else ''} ({r['load']:g} bricks) at {r['lever']:g} studs out "
                     f"-> risk {r['risk']:g}")
    lines.append("Fixes: more studs on the link (a wider plate across the joint), a second link "
                 "(a bracket, another plate or a joint elsewhere), a stronger joint (large ball, "
                 "4-stud base), or lighter / shorter overhangs.")
    return "\n".join(lines)
