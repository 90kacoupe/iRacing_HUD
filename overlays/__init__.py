"""The overlays the app runs. Add new ones here."""
import importlib
import traceback

OVERLAYS = [
    ("overlays.dash", "DashOverlay"),
    ("overlays.side_indicator", "SideIndicatorOverlay"),
    ("overlays.pit_board", "PitBoardOverlay"),
    ("overlays.team_board", "TeamBoardOverlay"),
]


def load_overlay_classes():
    """Import each overlay on its own, so one broken overlay can't stop the rest."""
    classes, errors = [], []
    for module, name in OVERLAYS:
        try:
            classes.append(getattr(importlib.import_module(module), name))
        except Exception:
            print(f"Couldn't load {module}:")
            traceback.print_exc()
            errors.append(module)
    return classes, errors
