"""Telemetry -> the dash values: a dict for the overlay's native dash, and the JSON the
HTML dash pages read from /data (same fields as the old dash_overlay.py)."""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DASHES_DIR = os.path.join(HERE, "dashes")

VARS = ("DisplayUnits", "Gear", "Speed", "FuelLevel", "OilPress", "WaterTemp",
        "LFcoldPressure", "RFcoldPressure", "LRcoldPressure", "RRcoldPressure",
        "LapDeltaToSessionBestLap", "LapDeltaToSessionBestLap_OK", "RPM", "LapLastLapTime",
        "LapBestLapTime", "LapCompleted", "dcTractionControl", "dcThrottleShape",
        "IsOnTrack", "IsReplayPlaying", "EngineWarnings", "dcBrakeBias", "Throttle")


def build_payload(frame, units_setting="auto"):
    """The /data JSON for the HTML dash pages (browsers and dash screens)."""
    return json.dumps(build_data(frame, units_setting)).encode()


def build_data(frame, units_setting="auto"):
    """The dash values as a dict: used by the overlay's native dash and by /data."""
    v = frame.vars.get
    units = units_setting
    if units == "auto":
        units = "metric" if v("DisplayUnits") == 1 else "imperial"
    imp = units == "imperial"

    gear = v("Gear")
    gear_txt = "R" if gear == -1 else "N" if gear in (0, None) else str(gear)
    speed, fuel, oil, water = v("Speed"), v("FuelLevel"), v("OilPress"), v("WaterTemp")

    def tyre(name):  # kPa
        p = v(name)
        return None if p is None else (p * 0.145038 if imp else p)

    delta = v("LapDeltaToSessionBestLap") if v("LapDeltaToSessionBestLap_OK") else None
    throttle = v("Throttle")

    data = {
        "connected": True,
        "Units": units,
        "Rpms": v("RPM"),
        "Gear": gear_txt,
        "Speed": None if speed is None else speed * (2.23694 if imp else 3.6),
        "LastLapTime": v("LapLastLapTime"),
        "BestLapTime": v("LapBestLapTime"),
        "Fuel": None if fuel is None else fuel * (0.264172 if imp else 1),
        "CompletedLaps": v("LapCompleted"),
        "OilPressure": None if oil is None else oil * (14.5038 if imp else 1),
        "WaterTemperature": None if water is None else (water * 9 / 5 + 32 if imp else water),
        "TyrePressureFrontLeft": tyre("LFcoldPressure"),
        "TyrePressureFrontRight": tyre("RFcoldPressure"),
        "TyrePressureRearLeft": tyre("LRcoldPressure"),
        "TyrePressureRearRight": tyre("RRcoldPressure"),
        "LapDeltaToSessionBestLap": delta,
        "dcTractionControl": v("dcTractionControl"),
        "dcThrottleShape": v("dcThrottleShape"),
        "IsOnTrack": bool(v("IsOnTrack")),
        "IsReplayPlaying": bool(v("IsReplayPlaying")),
        "PitLimiter": bool((v("EngineWarnings") or 0) & 0x10),   # iRacing's pit speed limiter flag
        "BrakeBias": v("dcBrakeBias"),
        "ThrottlePct": None if throttle is None else throttle * 100,
    }
    rain = frame.session.get("rain_var")
    if rain:
        data["dcRainLight"] = v(rain)
    data.update(frame.session.get("shift", {}))
    return data


def dash_file_for(car_path):
    """dashes/<car path>.html if it exists, otherwise dashes/default.html."""
    if car_path:
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", car_path) + ".html"
        if os.path.exists(os.path.join(DASHES_DIR, name)):
            return name
    return "default.html"
