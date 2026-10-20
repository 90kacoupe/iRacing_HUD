"""One iRacing reader for every overlay.

A background thread reads iRacing about 60 times a second and publishes a Frame.
Overlays never touch pyirsdk; they read frame.vars (the telemetry variables they
asked for in their VARS list) and frame.session (car, shift lights, track length).
"""
import re
import threading
import time

from .demo import DemoTraffic


class Frame:
    __slots__ = ("connected", "driving", "vars", "session", "stamp")

    def __init__(self, connected, driving, vars, session, stamp):
        self.connected = connected   # iRacing is running a session
        self.driving = driving       # in the car on track, not watching a replay
        self.vars = vars             # {telemetry name: value}
        self.session = session       # car_path, car_name, shift, track_len_m, rain_var, all_vars
        self.stamp = stamp


EMPTY = Frame(False, False, {}, {}, 0.0)


def parse_track_length_m(text):
    """'5.51 km' / '2.50 mi' -> metres."""
    try:
        num, unit = str(text).split()[:2]
        return float(num) * (1609.344 if unit.lower().startswith("mi") else 1000.0)
    except Exception:
        return 0.0


def read_session(ir):
    """Things that only change between sessions."""
    s = {"car_path": None, "car_name": None, "shift": {}, "rain_var": None,
         "all_vars": [], "track_len_m": 0.0, "drivers": {}, "est_lap_s": 0.0, "session_type": ""}
    try:
        info = ir["DriverInfo"] or {}
        me = info.get("DriverCarIdx")
        for drv in info.get("Drivers") or []:
            if drv.get("CarIdx") == me:
                s["car_path"] = drv.get("CarPath")
                s["car_name"] = drv.get("CarScreenName")
                break
        for k in ("DriverCarSLFirstRPM", "DriverCarSLShiftRPM", "DriverCarSLLastRPM", "DriverCarSLBlinkRPM"):
            if info.get(k):
                s["shift"][k] = info[k]
        if info.get("DriverCarRedLine"):
            s["shift"]["MaxRpm"] = info["DriverCarRedLine"]
        s["est_lap_s"] = float(info.get("DriverCarEstLapTime") or 0.0)
        from overlays.pit_board.relative import drivers_from_info
        s["drivers"] = drivers_from_info(info)
    except Exception:
        pass
    try:
        num = ir["SessionNum"]
        for sess in (ir["SessionInfo"] or {}).get("Sessions") or []:
            if sess.get("SessionNum") == num:
                s["session_type"] = str(sess.get("SessionType") or "")
                break
    except Exception:
        pass
    try:
        s["track_len_m"] = parse_track_length_m((ir["WeekendInfo"] or {}).get("TrackLength", ""))
    except Exception:
        pass
    try:
        names = sorted(getattr(ir, "_var_headers_dict", {}) or {})
        s["all_vars"] = names
        for n in names:
            if re.search(r"rain.?light", n, re.I):
                s["rain_var"] = n
                break
    except Exception:
        pass
    return s


def _get(ir, name):
    try:
        return ir[name]
    except Exception:
        return None


class IRacingTelemetry:
    HZ = 60

    def __init__(self, var_names):
        self.var_names = set(var_names) | {"IsOnTrack", "IsReplayPlaying"}
        self._latest = EMPTY
        self._lock = threading.Lock()
        self.error = None
        try:
            import irsdk  # noqa: F401
        except ImportError:
            self.error = "pyirsdk isn't installed, so there's no live data. Run setup.bat."
            print(self.error)
            return
        threading.Thread(target=self._run, daemon=True, name="telemetry").start()

    def latest(self):
        with self._lock:
            return self._latest

    def _set(self, frame):
        with self._lock:
            self._latest = frame

    def _run(self):
        import irsdk
        ir = irsdk.IRSDK()
        connected = False
        session, last_info, last_read = {}, None, 0.0
        errors = 0
        while True:
            try:
                if not connected:
                    if ir.startup() and ir.is_initialized and ir.is_connected:
                        connected, last_info = True, None
                    else:
                        self._set(EMPTY)
                        time.sleep(1)
                        continue
                if not (ir.is_initialized and ir.is_connected):
                    ir.shutdown()
                    connected, session = False, {}
                    self._set(EMPTY)
                    continue
                ir.freeze_var_buffer_latest()
                try:
                    upd = getattr(ir, "session_info_update", None)
                    if upd != last_info or time.time() - last_read > 10:
                        session, last_info, last_read = read_session(ir), upd, time.time()
                    names = self.var_names
                    if session.get("rain_var"):
                        names = names | {session["rain_var"]}
                    values = {n: _get(ir, n) for n in names}
                finally:
                    ir.unfreeze_var_buffer_latest()
                driving = bool(values.get("IsOnTrack")) and not values.get("IsReplayPlaying")
                self._set(Frame(True, driving, values, session, time.time()))
                errors = 0
            except Exception as e:
                errors += 1
                if errors <= 3:
                    print("telemetry error:", repr(e))
                time.sleep(0.5)
            time.sleep(1 / self.HZ)


class DemoTelemetry:
    """Pretends you're driving, with simulated traffic around you."""
    error = None

    def __init__(self):
        self.traffic = DemoTraffic()
        self.session = {"car_path": "demo", "car_name": "Demo car", "shift": {}, "rain_var": None,
                        "all_vars": [], "track_len_m": DemoTraffic.TRACK, "drivers": {},
                        "est_lap_s": 90.0, "session_type": "Race"}

    def latest(self):
        return Frame(True, True, self.traffic.as_vars(), self.session, time.time())
