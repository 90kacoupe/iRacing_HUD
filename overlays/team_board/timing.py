"""Team pit board timing: what a race team would put on the board each lap.
No Qt here, so it can be tested on its own.

Like a real team, it times every car as it crosses the start/finish line and puts the
result on the board once per lap, just after you cross the line:

  * Gap to the car ahead in position (your class): measured at the line this lap.
  * Gap to the car behind in position: measured when they crossed the line after you
    last lap (they haven't reached the line yet this lap). Real teams do the same: the
    board is made up from the last time both cars passed the pit wall.
  * Trend: how much you gained or lost on each since the last board.
  * Cars nearest you on track (any class, lapped traffic too), at the moment of the board.
  * Lap number, laps or time to go, your last lap.

In practice and qualifying the gaps are to the best laps of the cars either side of you
in the times, the way a qualifying board works.
"""
import math

from overlays.pit_board.relative import build_relative, wrap

UNLIMITED_LAPS = 32767


def fmt_laptime(s):
    if not s or s <= 0:
        return "--"
    m, sec = divmod(s, 60.0)
    return f"{int(m)}:{sec:06.3f}" if m else f"{sec:.3f}"


def fmt_remaining(laps_left, time_left):
    if laps_left is not None and 0 <= laps_left < UNLIMITED_LAPS:
        return "LAST LAP" if laps_left == 0 else f"{laps_left} TO GO"
    if time_left is not None and 0 <= time_left < 604800:
        mins = int(math.ceil(time_left / 60.0))
        return f"{mins // 60}H{mins % 60:02d}" if mins >= 60 else f"{mins} MIN"
    return ""


class Gap:
    __slots__ = ("idx", "number", "seconds", "laps", "trend", "estimated")

    def __init__(self, idx, number, seconds, laps=0, trend=None, estimated=False):
        self.idx = idx
        self.number = number
        self.seconds = seconds      # always positive: how far apart
        self.laps = laps            # whole laps apart (lapped / lapping), 0 = same lap
        self.trend = trend          # + = you gained since the last board, - = you lost, None = n/a
        self.estimated = estimated  # True = not measured at the line yet (first lap, etc.)

    def __repr__(self):
        return f"Gap(#{self.number} {self.seconds:.2f}s laps={self.laps} trend={self.trend})"


class Board:
    """One pit board's worth of information."""

    def __init__(self):
        self.pos = 0
        self.class_name = ""
        self.ahead = None           # Gap, or None when you lead
        self.behind = None          # Gap, or None when you're last
        self.track_ahead = None     # pit_board.relative.Row or None
        self.track_behind = None
        self.lap = 0
        self.remaining = ""
        self.last_lap = 0.0
        self.qualifying = False
        self.stamp = 0.0            # session time the board went out

    def __repr__(self):
        return (f"Board(P{self.pos} {self.class_name} ahead={self.ahead} behind={self.behind} "
                f"L{self.lap} {self.remaining} last={fmt_laptime(self.last_lap)})")


def _at(lst, i, default=None):
    return lst[i] if lst is not None and i < len(lst) and lst[i] is not None else default


class LapTimer:
    CROSS_HI, CROSS_LO = 0.85, 0.15

    def __init__(self):
        self.reset()

    def reset(self):
        self.prev = {}            # car idx -> (pct, session time)
        self.last_cross = {}      # car idx -> session time of their latest line crossing
        self.my_cross = None      # session time of my latest crossing
        self.behind_meas = {}     # car idx -> seconds they crossed after me, this lap
        self.behind_last = {}     # the same, for the lap I just finished
        self.prev_ahead = {}      # car idx -> last gap shown to them (for the trend)
        self.prev_behind = {}
        self.pending = None       # session time to put out the next board
        self.last_t = None
        self.board = None

    # ---- line crossings ------------------------------------------------------------
    def _crossings(self, v, t):
        """[(car idx, crossing time)] for cars that crossed the line since the last frame."""
        pcts = v.get("CarIdxLapDistPct") or []
        out = []
        for i, pct in enumerate(pcts):
            if pct is None or pct < 0:
                self.prev.pop(i, None)
                continue
            old = self.prev.get(i)
            self.prev[i] = (pct, t)
            if old is None:
                continue
            p0, t0 = old
            if p0 > self.CROSS_HI and pct < self.CROSS_LO and t > t0:
                k = (1.0 - p0) / max(1e-6, (1.0 - p0) + pct)   # where between frames it crossed
                out.append((i, t0 + (t - t0) * k))
        return out

    def update(self, v, session, delay_s=1.0):
        """Feed every frame. Returns a new Board when one goes out, else None."""
        t = v.get("SessionTime")
        me = v.get("PlayerCarIdx")
        if t is None or me is None:
            return None
        if self.last_t is not None and t < self.last_t - 1.0:
            self.reset()                       # new session
        if self.last_t is not None and t == self.last_t:
            return None
        self.last_t = t

        lap_s = float(session.get("est_lap_s") or 0.0) or 90.0
        for i, tc in self._crossings(v, t):
            self.last_cross[i] = tc
            if i == me:
                self.behind_last, self.behind_meas = self.behind_meas, {}
                self.my_cross = tc
                self.pending = t + delay_s     # give iRacing a moment to update positions / lap times
            elif self.my_cross is not None and 0 < tc - self.my_cross < lap_s * 0.95:
                self.behind_meas[i] = tc - self.my_cross

        if self.pending is not None and t >= self.pending:
            self.pending = None
            self.board = self.make_board(v, session)
            return self.board
        return None

    # ---- the board -----------------------------------------------------------------
    def _class_order(self, v, session, me):
        """Cars in my class, best position first: [(idx, class position)]."""
        drivers = session.get("drivers") or {}
        my_class = (drivers.get(me) or {}).get("class_id")
        cpos = v.get("CarIdxClassPosition") or []
        lc = v.get("CarIdxLapCompleted") or []
        pcts = v.get("CarIdxLapDistPct") or []
        cars = []
        for i, pct in enumerate(pcts):
            d = drivers.get(i) or {}
            if d.get("pace_car") or d.get("spectator"):
                continue
            if my_class is not None and d.get("class_id") is not None and d.get("class_id") != my_class:
                continue
            if (pct is None or pct < 0) and i != me:
                continue
            cars.append(i)
        have_pos = all(_at(cpos, i, 0) > 0 for i in cars)
        if have_pos:
            cars.sort(key=lambda i: _at(cpos, i, 999))
        else:   # before official positions exist: by distance covered
            cars.sort(key=lambda i: -(_at(lc, i, 0) + max(0.0, _at(pcts, i, 0.0))))
        return [(i, _at(cpos, i, 0) if have_pos else n + 1) for n, i in enumerate(cars)]

    def make_board(self, v, session):
        me = v.get("PlayerCarIdx")
        drivers = session.get("drivers") or {}
        b = Board()
        b.stamp = v.get("SessionTime") or 0.0
        b.qualifying = str(session.get("session_type", "")).lower() not in ("race", "")
        b.class_name = (drivers.get(me) or {}).get("class_short", "")
        lc = v.get("CarIdxLapCompleted") or []
        b.lap = _at(lc, me, v.get("LapCompleted") or 0) + 1
        b.remaining = fmt_remaining(v.get("SessionLapsRemainEx"), v.get("SessionTimeRemain"))
        b.last_lap = v.get("LapLastLapTime") or _at(v.get("CarIdxLastLapTime"), me, 0.0) or 0.0
        lap_s = float(session.get("est_lap_s") or 0.0) or 90.0

        order = self._class_order(v, session, me)
        idxs = [i for i, _ in order]
        if me in idxs:
            k = idxs.index(me)
            b.pos = order[k][1]
            ahead = idxs[k - 1] if k > 0 else None
            behind = idxs[k + 1] if k + 1 < len(idxs) else None
        else:
            ahead = behind = None

        def number(i):
            return (drivers.get(i) or {}).get("number", str(i))

        def trend_for(store, i, gap, sign):
            old = store.get(i)
            store.clear()
            store[i] = gap
            return None if old is None else round(sign * (gap - old), 3)

        if b.qualifying:
            best = v.get("CarIdxBestLapTime") or []
            mine = _at(best, me, 0.0)
            for i, attr, sign in ((ahead, "ahead", -1), (behind, "behind", +1)):
                if i is None:
                    continue
                theirs = _at(best, i, 0.0)
                if mine > 0 and theirs > 0:
                    secs = abs(mine - theirs)
                    store = self.prev_ahead if attr == "ahead" else self.prev_behind
                    setattr(b, attr, Gap(i, number(i), secs, 0, trend_for(store, i, secs, sign)))
                else:
                    setattr(b, attr, Gap(i, number(i), 0.0, 0, None, estimated=True))
        else:
            my_lc = _at(lc, me, 0)
            est = v.get("CarIdxEstTime") or []
            pcts = v.get("CarIdxLapDistPct") or []

            def estimate(i):
                mine, theirs = _at(est, me), _at(est, i)
                if mine is not None and theirs is not None:
                    return abs(wrap(theirs - mine, lap_s))
                return abs(wrap(_at(pcts, i, 0.0) - _at(pcts, me, 0.0), 1.0)) * lap_s

            if ahead is not None:
                laps = max(0, _at(lc, ahead, my_lc) - my_lc)
                tc = self.last_cross.get(ahead)
                if tc is not None and self.my_cross is not None and 0 <= self.my_cross - tc < lap_s * 1.5:
                    secs, est_flag = self.my_cross - tc, False
                else:
                    secs, est_flag = estimate(ahead), True
                if laps:
                    secs = max(0.0, secs)
                trend = None if laps else trend_for(self.prev_ahead, ahead, secs, -1)
                b.ahead = Gap(ahead, number(ahead), secs, laps, trend, est_flag)
            if behind is not None:
                # They haven't crossed yet this lap, so their completed laps are one fewer.
                laps = max(0, my_lc - 1 - _at(lc, behind, my_lc - 1))
                meas = self.behind_meas.get(behind, self.behind_last.get(behind))
                if meas is not None:
                    secs, est_flag = meas, False
                else:
                    secs, est_flag = estimate(behind), True
                trend = None if laps else trend_for(self.prev_behind, behind, secs, +1)
                b.behind = Gap(behind, number(behind), secs, laps, trend, est_flag)

        rel = build_relative(v, session, 1, 1)
        if rel:
            a, _, bh = rel
            b.track_ahead = a[-1] if a else None
            b.track_behind = bh[0] if bh else None
        return b


class DemoBoards:
    """Made-up boards for layout mode, demo mode and the preview button: a new one every 8 s."""

    def __init__(self, t0):
        self.t0 = t0
        self.n = -1
        self.board = None

    def read(self, now):
        from overlays.pit_board.relative import Row
        n = int((now - self.t0) // 8)
        if n != self.n:
            self.n = n
            b = Board()
            b.pos, b.class_name, b.lap = 4, "GT3", 12 + n
            b.remaining = f"{max(0, 18 - n)} TO GO"
            b.last_lap = 107.412 + 0.35 * math.sin(n * 1.7)
            ga = max(0.2, 1.8 - 0.25 * n + 0.2 * math.sin(n))
            gb = max(0.2, 0.9 + 0.15 * math.sin(n * 2.3))
            b.ahead = Gap(1, "22", ga, 0, None if n == 0 else round(0.25 - 0.2 * math.cos(n), 2))
            b.behind = Gap(2, "7", gb, 0, None if n == 0 else round(0.3 * math.sin(n * 2.3), 2))
            b.track_ahead = Row(3, 2.6, 0, "88", "R. Calder", (255, 218, 89), False, False, -1, False)
            b.track_behind = Row(4, -1.1, 0, "6", "T. Moreau", (51, 206, 255), False, False, 1, False)
            b.stamp = now
            self.board = b
            return b, True
        return self.board, False
