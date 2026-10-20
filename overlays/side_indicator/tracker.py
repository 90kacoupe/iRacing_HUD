"""Which nearby cars are on which side, and where (no Qt here, so it can be tested on its own).

* Which side(s):   iRacing's CarLeftRight (the spotter's own data).
* How far up/down: the lap-distance gap to nearby cars x track length. iRacing doesn't
  say where other cars are sideways, so a car gets the side the spotter first called
  and keeps it while it stays alongside.
"""

# iRacing CarLeftRight values -> (cars on left, cars on right)
CLR_COUNTS = {
    0: (0, 0),  # off
    1: (0, 0),  # clear
    2: (1, 0),  # car left
    3: (0, 1),  # car right
    4: (1, 1),  # car left and right
    5: (2, 0),  # two cars left
    6: (0, 2),  # two cars right
}

UNKNOWN = None  # placeholder delta: the spotter sees a car we can't place


def lap_delta_m(their_pct, my_pct, track_len_m):
    """Signed distance in metres from my car to theirs (+ = they are ahead)."""
    d = (their_pct - my_pct + 0.5) % 1.0 - 0.5
    return d * track_len_m


class SideTracker:
    def __init__(self, car_length_m=4.7):
        self.sides = {}  # car idx -> "L" / "R"
        self.set_car_length(car_length_m)

    def set_car_length(self, car_length_m):
        self.car_length = car_length_m
        self.search_m = car_length_m * 2.0  # how far to look for candidates

    def update(self, clr, my_pct, others, track_len_m):
        """Returns (left, right): lists of deltas in metres (+ = ahead) or UNKNOWN."""
        need_l, need_r = CLR_COUNTS.get(clr, (0, 0))
        if need_l == 0 and need_r == 0 or my_pct is None or my_pct < 0:
            self.sides.clear()
            if need_l or need_r:
                return [UNKNOWN] * need_l, [UNKNOWN] * need_r
            return [], []

        near = {}
        if track_len_m and track_len_m > 0:
            for idx, pct in others.items():
                if pct is None or pct < 0:
                    continue
                d = lap_delta_m(pct, my_pct, track_len_m)
                if abs(d) <= self.search_m:
                    near[idx] = d

        self.sides = {i: s for i, s in self.sides.items() if i in near}   # forget cars that left

        by_dist = sorted(near, key=lambda i: abs(near[i]))
        left = [i for i in by_dist if self.sides.get(i) == "L"]
        right = [i for i in by_dist if self.sides.get(i) == "R"]

        for lst, need in ((left, need_l), (right, need_r)):   # spotter now reports fewer
            while len(lst) > need:
                self.sides.pop(lst.pop(), None)

        for i in by_dist:                                      # fill empty slots, closest first
            if i in self.sides:
                continue
            if len(left) < need_l:
                left.append(i)
                self.sides[i] = "L"
            elif len(right) < need_r:
                right.append(i)
                self.sides[i] = "R"

        out_l = sorted(near[i] for i in left) + [UNKNOWN] * (need_l - len(left))
        out_r = sorted(near[i] for i in right) + [UNKNOWN] * (need_r - len(right))
        return out_l, out_r


def side_data_from_vars(v, track_len_m):
    """Telemetry vars -> (clr, my_pct, others, track_len_m), or None when it can't be read."""
    clr = v.get("CarLeftRight") or 0
    me = v.get("PlayerCarIdx")
    pcts = v.get("CarIdxLapDistPct") or []
    locs = v.get("CarIdxTrackSurface") or []
    pits = v.get("CarIdxOnPitRoad") or []
    if me is None or me >= len(pcts):
        return None
    my_pit = pits[me] if me < len(pits) else False
    others = {}
    for i, pct in enumerate(pcts):
        if i == me or pct is None or pct < 0:
            continue
        loc = locs[i] if i < len(locs) else 3
        if loc not in (0, 3):  # only cars on track (or just off it)
            continue
        if (pits[i] if i < len(pits) else False) != my_pit:
            continue
        others[i] = pct
    return clr, pcts[me], others, track_len_m
