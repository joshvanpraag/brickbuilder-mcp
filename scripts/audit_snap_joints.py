"""Audit the joints added from the LDCad snap data against each part's real shape.

For every part, each snap-derived joint's centre is measured against the part's drawn
surface (its LDraw triangles). The surface should be about one connector radius away:
  bar / pin / axle:        the joint sits on the axis of a cylinder of that radius
  pin_hole / axle_hole:    the centre is open (nothing crosses it) with the wall around it
  clip / ball / socket / finger: the surface that grips is right around the centre
The server keeps only joints that pass (snaps.plausible); this report shows how many
each kind loses and which parts they are on. Run from the brickbuilder-mcp folder:
    uv run python scripts/audit_snap_joints.py [report.txt]
"""
import collections
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from brickbuilder import geometry, part_index

from brickbuilder.snaps import plausible  # noqa: E402


def check(pid):
    try:
        # every candidate the snap data gives, before the server drops the ones that fail
        out = []
        for k, o, f, s in geometry._snap_joints(pid, [], validate=False):
            ok, d = plausible(pid, k, o)
            out.append((k, ok, f"surface {d:.1f} LDU from the joint centre"))
        return pid, out
    except Exception as e:
        return pid, [("error", False, str(e)[:80])]


if __name__ == "__main__":
    recs = part_index._load()
    ids = [p for p, r in recs.items() if r.get("kind") == "part"]
    t = time.time()
    with ProcessPoolExecutor() as pool:
        res = list(pool.map(check, ids, chunksize=32))
    tally = collections.defaultdict(lambda: [0, 0])
    bad = collections.defaultdict(list)
    for pid, rows in res:
        for k, ok, why in rows:
            tally[k][0 if ok else 1] += 1
            if not ok:
                bad[k].append(f"{pid} ({recs[pid]['title'][:40]}): {why}")
    lines = [f"Audited {len(ids)} parts in {time.time() - t:.0f}s", "kind: kept / dropped (did not match the part's shape)"]
    lines += [f"  {k:12} {v[0]:5} / {v[1]}" for k, v in sorted(tally.items())]
    cats = collections.defaultdict(collections.Counter)
    for pid, rows in res:
        for k, ok, why in rows:
            if not ok:
                cats[k][recs[pid].get("category", "?")] += 1
    summary = ["dropped, by part category:"]
    summary += [f"  {k:12} " + ", ".join(f"{c} {n}" for c, n in cats[k].most_common(8)) for k in sorted(cats)]
    lines += summary
    for k, rows in sorted(bad.items()):
        lines.append(f"\nsuspect {k} ({len(rows)}):")
        lines += ["  " + r for r in rows]
    text = "\n".join(lines)
    print(text if len(sys.argv) < 2 else "\n".join(lines[:2 + len(tally) + len(summary)]))
    if len(sys.argv) > 1:
        open(sys.argv[1], "w", encoding="utf-8").write(text)
