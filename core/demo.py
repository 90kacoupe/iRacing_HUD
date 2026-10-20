"""Simulated traffic, so the overlays can be seen without iRacing (demo mode, test sweep, layout mode)."""
import math
import time

CAR_LENGTH_M = 4.7


class DemoTraffic:
    TRACK = 4000.0

    def __init__(self, loop_s=24.0, start=None, car_length_m=CAR_LENGTH_M):
        self.loop_s = loop_s
        self.car_length = car_length_m
        self.t0 = time.monotonic() if start is None else start

    def scene(self, t):
        """[(idx, delta_m, side)] for the cars around us at time t."""
        L = self.car_length
        p = t % self.loop_s
        cars = []

        def sweep(t_start, dur, frm, to, side, idx):
            if t_start <= p < t_start + dur:
                k = (p - t_start) / dur
                k = 0.5 - 0.5 * math.cos(math.pi * k)  # ease in/out
                cars.append((idx, frm + (to - frm) * k, side))

        sweep(0.0, 5.0, -2.0 * L, 2.0 * L, "L", 1)      # car passes you on the left
        sweep(6.0, 5.0, 2.0 * L, -2.0 * L, "R", 2)      # you pass a car on the right
        sweep(12.0, 5.0, -1.8 * L, 0.3 * L, "L", 3)     # side by side both sides
        sweep(12.5, 4.5, 1.9 * L, -0.4 * L, "R", 4)
        sweep(18.0, 5.0, -2.2 * L, 1.0 * L, "L", 5)     # two cars on the left
        sweep(18.0, 5.0, -3.4 * L, -0.2 * L, "L", 6)
        return cars

    def read(self, now=None):
        """(CarLeftRight, my_pct, {idx: pct}, track_len_m), the same shape as live data."""
        t = (time.monotonic() if now is None else now) - self.t0
        cars = self.scene(t)
        my_pct = 0.25
        alongside = [(i, d, s) for i, d, s in cars if abs(d) < self.car_length]
        nl = sum(1 for _, _, s in alongside if s == "L")
        nr = len(alongside) - nl
        clr = {(0, 0): 1, (1, 0): 2, (0, 1): 3, (1, 1): 4, (2, 0): 5,
               (0, 2): 6}.get((min(nl, 2), min(nr, 2)), 4)
        others = {i: my_pct + d / self.TRACK for i, d, _ in cars}
        return clr, my_pct, others, self.TRACK

    def as_vars(self, now=None):
        """The same traffic as iRacing telemetry variables."""
        clr, my_pct, others, _ = self.read(now)
        n = 8
        pcts = [-1.0] * n
        pcts[0] = my_pct
        for i, p in others.items():
            pcts[i] = p
        return {"CarLeftRight": clr, "PlayerCarIdx": 0, "CarIdxLapDistPct": pcts,
                "CarIdxTrackSurface": [3] * n, "CarIdxOnPitRoad": [False] * n,
                "IsOnTrack": True, "IsReplayPlaying": False}
