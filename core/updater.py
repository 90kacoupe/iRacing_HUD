"""Update checks against the GitHub releases of this app (no account or sign-in needed).

The Qt side (when to check, the notification, the dialog) is in core/update_ui.py.
"""
import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.request

from .version import REPO, VERSION

API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
USER_AGENT = f"SimRacingHUD/{VERSION}"


def parse_version(text):
    """'v1.2.3' -> (1, 2, 3). Missing parts count as 0."""
    nums = [int(n) for n in re.findall(r"\d+", str(text or ""))[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def is_newer(version, than=VERSION):
    return parse_version(version) > parse_version(than)


class Release:
    def __init__(self, version, notes, installer_url, installer_name, size, page):
        self.version = version
        self.notes = notes
        self.installer_url = installer_url
        self.installer_name = installer_name
        self.size = size
        self.page = page


def _get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_latest(timeout=15):
    """The latest published release, or None if there isn't one yet. Raises on network errors."""
    try:
        with _get(API_LATEST, timeout) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:          # no releases yet
            return None
        raise
    if data.get("draft") or data.get("prerelease"):
        return None
    installer = None
    for a in data.get("assets") or []:
        name = a.get("name", "")
        if name.lower().endswith(".exe") and "setup" in name.lower():
            installer = a
            break
    return Release(
        version=str(data.get("tag_name") or "").lstrip("vV"),
        notes=(data.get("body") or "").strip(),
        installer_url=installer.get("browser_download_url") if installer else None,
        installer_name=installer.get("name") if installer else None,
        size=int(installer.get("size") or 0) if installer else 0,
        page=data.get("html_url") or RELEASES_PAGE,
    )


def download(release, progress=None, cancelled=lambda: False):
    """Download the installer to the temp folder. progress(done_bytes, total_bytes)."""
    folder = os.path.join(tempfile.gettempdir(), "SimRacingHUD-update")
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, release.installer_name or f"SimRacingHUD-Setup-{release.version}.exe")
    part = dest + ".part"
    with _get(release.installer_url, 60) as r, open(part, "wb") as f:
        total = int(r.headers.get("Content-Length") or release.size or 0)
        done = 0
        while True:
            if cancelled():
                raise InterruptedError("cancelled")
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    if total and done != total:
        raise IOError(f"download incomplete ({done} of {total} bytes)")
    os.replace(part, dest)
    return dest


def run_installer(path):
    """Start the installer quietly. It closes this app if needed, updates, and starts it again."""
    flags = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
                     close_fds=True, creationflags=flags)
