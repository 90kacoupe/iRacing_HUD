"""Pit board logic: when to show it, and the time gaps to the cars around you.
No Qt here, so it can be tested on its own.

When it shows (any of these):
  * the pit speed limiter is on
  * you're stopped on track (e.g. after a spin) for a moment
  * optionally: anywhere on pit road
...and it stays up for a few seconds after, so you can see the gap while you rejoin.

Gaps: iRacing's CarIdxEstTime is how long a car at normal pace takes to get from the
start/finish line to where it is now. The difference between theirs and yours is how
many seconds ahead or behind they are at racing speed, which is exactly what you want
when you're stopped: a car 2.5 s behind arrives in about 2.5 s.
"""

LIMITER_BIT = 0x10        # EngineWarnings: pit speed limiter on
SURF_NOT_IN_WORLD = -1
SURF_OFF_TRACK = 0
SURF_IN_PIT_STALL = 1
SURF_APPROACHING_PITS = 2
SURF_ON_TRACK = 3
STATE_RACING = 4          # SessionState: green flag (also used through practice / qualifying)

REASON_LIMITER = "limiter"
REASON_STOPPED = "stopped"
REASON_PIT_ROAD = "pit_road"
REASON_PEEK = "peek"


def wrap(d, period):
    """Fold a gap into -period/2 .. +period/2."""
    if not period or period <= 0:
        return d
    return (d + period / 2.0) % period - period / 2.0


class Trigger:
    """Decides when the pit board is up. Call update() every frame."""

    def __init__(self):
        self.stopped_since = None
        self.last_reason = None
        self.linger_until = 0.0
        self.peek_until = 0.0

    def peek(self, now, seconds):
        self.peek_until = now + seconds

    def reset(self):
        self.stopped_since = None
        self.last_reason = None
        self.linger_until = 0.0

    def live_reason(self, v, cfg, now):
        """Why it should show right now, or None. v = telemetry vars."""
        if cfg["on_limiter"] and (v.get("EngineWarnings") or 0) & LIMITER_BIT:
            self.stopped_since = None
            return REASON_LIMITER
        on_pit_road = bool(v.get("OnPitRoad"))
        if cfg["on_pit_road"] and on_pit_road:
            self.stopped_since = None
            return REASON_PIT_ROAD
        speed = v.get("Speed")
        stopped = speed is not None and abs(speed) * 3.6 <= float(cfg["stopped_kph"])
        if cfg["on_stopped"] and stopped and not on_pit_road:
            state = v.get("SessionState")
            if cfg["skip_grid"] and state is not None and state < STATE_RACING:
                self.stopped_since = None        # lined up on the grid / waiting for green
                return None
            self.stopped_since = self.stopped_since if self.stopped_since is not None else now
            if now - self.stopped_since >= float(cfg["stopped_for_s"]):
                return REASON_STOPPED
            return None
        self.stopped_since = None
        return None

    def update(self, v, cfg, now):
        """(showing, reason). reason is the last trigger while it lingers."""
        reason = self.live_reason(v, cfg, now)
        if reason:
            self.last_reason = reason
            self.linger_until = now + float(cfg["linger_s"])
            return True, reason
        if now < self.linger_until and self.last_reason:
            return True, self.last_reason
        if now < self.peek_until:
            return True, REASON_PEEK
        self.last_reason = None
        return False, None


class Row:
    __slots__ = ("idx", "gap", "pos", "number", "name", "class_color", "in_pit", "off_track",
                 "lap_diff", "is_me")

    def __init__(self, idx, gap, pos, number, name, class_color, in_pit, off_track, lap_diff, is_me):
        self.idx = idx
        self.gap = gap                  # seconds, + = ahead of you on track
        self.pos = pos                  # class position, 0 = none
        self.number = number
        self.name = name
        self.class_color = class_color  # (r, g, b) or None
        self.in_pit = in_pit
        self.off_track = off_track
        self.lap_diff = lap_diff        # +1 = a lap (or more) up on you, -1 = a lap down, 0 = same lap
        self.is_me = is_me

    def __repr__(self):
        return f"Row({self.number} {self.name} {self.gap:+.1f})"


def short_name(full):
    """'Max Verstappen' -> 'M. Verstappen'."""
    parts = str(full or "").split()
    if len(parts) >= 2:
        return f"{parts[0][0]}. {' '.join(parts[1:])}"
    return parts[0] if parts else ""


def class_rgb(value):
    try:
        n = int(value, 16) if isinstance(value, str) else int(value)
        return ((n >> 16) & 255, (n >> 8) & 255, n & 255) if n else None
    except Exception:
        return None


def _list(v, name):
    x = v.get(name)
    return list(x) if x is not None else []


def build_relative(v, session, ahead=3, behind=3):
    """Telemetry -> (rows ahead (closest last), my row, rows behind (closest first)).
    Returns None when there's not enough data."""
    me = v.get("PlayerCarIdx")
    pcts = _list(v, "CarIdxLapDistPct")
    if me is None or me >= len(pcts) or pcts[me] is None or pcts[me] < 0:
        return None
    est = _list(v, "CarIdxEstTime")
    laps = _list(v, "CarIdxLap")
    surf = _list(v, "CarIdxTrackSurface")
    pit = _list(v, "CarIdxOnPitRoad")
    cpos = _list(v, "CarIdxClassPosition")
    drivers = session.get("drivers") or {}
    is_race = session.get("session_type", "").lower() == "race"

    lap_s = float(session.get("est_lap_s") or 0.0)
    if lap_s <= 0:
        lap_s = max(30.0, float(session.get("track_len_m") or 0.0) / 45.0) or 90.0

    def at(lst, i, default=None):
        return lst[i] if i < len(lst) and lst[i] is not None else default

    def make(i, gap):
        d = drivers.get(i, {})
        lap_diff = 0
        if is_race and i != me:
            mine = at(laps, me, 0) + pcts[me]
            theirs = at(laps, i, 0) + pcts[i]
            total = theirs - mine
            if total > 0.5:
                lap_diff = 1
            elif total < -0.5:
                lap_diff = -1
        return Row(i, gap, at(cpos, i, 0), d.get("number", str(i)), d.get("name", f"Car {i}"),
                   d.get("class_color"), bool(at(pit, i, False)),
                   at(surf, i, SURF_ON_TRACK) == SURF_OFF_TRACK, lap_diff, i == me)

    my_est = at(est, me)
    others = []
    for i, pct in enumerate(pcts):
        if i == me or pct is None or pct < 0:
            continue
        if at(surf, i, SURF_ON_TRACK) == SURF_NOT_IN_WORLD:
            continue
        d = drivers.get(i)
        if d is not None and (d.get("pace_car") or d.get("spectator")):
            continue
        their_est = at(est, i)
        if my_est is not None and their_est is not None and (my_est or their_est):
            gap = wrap(their_est - my_est, lap_s)
        else:
            gap = wrap(pct - pcts[me], 1.0) * lap_s
        others.append(make(i, gap))

    ahead_rows = sorted([r for r in others if r.gap >= 0], key=lambda r: r.gap)[:ahead]
    behind_rows = sorted([r for r in others if r.gap < 0], key=lambda r: -r.gap)[:behind]
    return list(reversed(ahead_rows)), make(me, 0.0), behind_rows


def drivers_from_info(info):
    """DriverInfo (session YAML) -> {car idx: {...}} for the pit board."""
    out = {}
    for d in (info or {}).get("Drivers") or []:
        idx = d.get("CarIdx")
        if idx is None:
            continue
        out[idx] = {
            "number": str(d.get("CarNumber") or idx),
            "name": short_name(d.get("UserName")),
            "class_color": class_rgb(d.get("CarClassColor")),
            "class_id": d.get("CarClassID"),
            "class_short": str(d.get("CarClassShortName") or ""),
            "pace_car": bool(d.get("CarIsPaceCar")),
            "spectator": bool(d.get("IsSpectator")),
        }
    return out


class DemoRelative:
    """Made-up cars and a made-up reason for layout mode, demo mode and the preview button."""
    CARS = [(1, "7", "R. Calder", 0xffda59), (2, "22", "T. Moreau", 0xffda59),
            (3, "4", "J. Okafor", 0x33ceff), (4, "88", "L. Brandt", 0xffda59),
            (5, "13", "M. Silva", 0x33ceff), (6, "51", "D. Novak", 0xffda59),
            (7, "3", "E. Lindqvist", 0xffda59)]
    BASE_GAPS = [5.9, 3.1, 0.9, -1.4, -2.6, -4.8, -8.2]

    def __init__(self, t0):
        self.t0 = t0

    def read(self, now, ahead=3, behind=3):
        import math
        t = now - self.t0
        rows = []
        for k, (idx, num, name, col) in enumerate(self.CARS):
            gap = self.BASE_GAPS[k] + 0.6 * math.sin(t * 0.5 + k)
            rows.append(Row(idx, gap, k + 2 if k < 3 else k + 3, num, name, class_rgb(col),
                            k == 5, False, -1 if k == 6 else 0, False))
        me = Row(0, 0.0, 5, "17", "You", (255, 218, 89), False, False, 0, True)
        a = sorted([r for r in rows if r.gap >= 0], key=lambda r: r.gap)[:ahead]
        b = sorted([r for r in rows if r.gap < 0], key=lambda r: -r.gap)[:behind]
        reason = REASON_LIMITER if int(t // 6) % 2 == 0 else REASON_STOPPED
        return (list(reversed(a)), me, b), reason
