"""
TrueHour — Background Update Checker with Channel-Aware Version Comparison.

Queries the GitHub Releases API in a background thread and compares the
latest available version against the currently running version.  Handles
release channels correctly:

  ┌──────────┬────────────────────────────────────────────────────┐
  │ Running  │ Notified about                                    │
  ├──────────┼────────────────────────────────────────────────────┤
  │ stable   │ newer stable only (ignores alpha/beta/rc)         │
  │ rc       │ newer rc or stable                                │
  │ beta     │ newer beta, rc, or stable                         │
  │ alpha    │ newer alpha, beta, rc, or stable                  │
  └──────────┴────────────────────────────────────────────────────┘

Channel ordering:  alpha < beta < rc < stable
"""

import re
import logging
import threading
from dataclasses import dataclass, field
from typing import Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

# ── Semantic Version Parsing ─────────────────────────────────────────

# Canonical channel ranking (higher = more stable)
CHANNEL_RANK = {
    "alpha": 0,
    "beta": 1,
    "rc": 2,
    "stable": 3,
}

# Regex for versions like: 3.1.1, 3.1.1-beta.2, 3.1.1-beta2, 3.1.1-alpha.1, 3.1.1-rc.3
_VERSION_RE = re.compile(
    r"^v?(\d+)\.(\d+)\.(\d+)"  # major.minor.patch
    r"(?:-(alpha|beta|rc)(?:\.?(\d+))?)?"  # optional -channel.N or -channelN
    r"$",
    re.IGNORECASE,
)


@dataclass(frozen=True, order=False)
class ParsedVersion:
    """A parsed semver with pre-release channel awareness."""

    major: int
    minor: int
    patch: int
    channel: str = "stable"  # alpha | beta | rc | stable
    pre_num: int = 0  # the .N in beta.N  (0 if absent)
    raw: str = ""  # original string for display

    @property
    def channel_rank(self) -> int:
        return CHANNEL_RANK.get(self.channel, 3)

    @property
    def sort_key(self) -> Tuple:
        """Comparable tuple: (major, minor, patch, channel_rank, pre_num)."""
        return (self.major, self.minor, self.patch, self.channel_rank, self.pre_num)

    def __lt__(self, other: "ParsedVersion") -> bool:
        return self.sort_key < other.sort_key

    def __le__(self, other: "ParsedVersion") -> bool:
        return self.sort_key <= other.sort_key

    def __gt__(self, other: "ParsedVersion") -> bool:
        return self.sort_key > other.sort_key

    def __ge__(self, other: "ParsedVersion") -> bool:
        return self.sort_key >= other.sort_key

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ParsedVersion):
            return NotImplemented
        return self.sort_key == other.sort_key

    @property
    def display(self) -> str:
        """Human-readable version string like 'v3.2.0' or 'v3.1.1-beta.3'."""
        base = f"v{self.major}.{self.minor}.{self.patch}"
        if self.channel != "stable":
            base += f"-{self.channel}"
            if self.pre_num > 0:
                base += f".{self.pre_num}"
        return base


def parse_version(raw: str) -> Optional[ParsedVersion]:
    """Parse a version string into a ParsedVersion, or None if unparseable."""
    if not raw:
        return None
    m = _VERSION_RE.match(raw.strip())
    if not m:
        return None
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    channel = (m.group(4) or "stable").lower()
    pre_num = int(m.group(5)) if m.group(5) else 0
    return ParsedVersion(
        major=major,
        minor=minor,
        patch=patch,
        channel=channel,
        pre_num=pre_num,
        raw=raw.strip(),
    )


def should_notify(current: ParsedVersion, candidate: ParsedVersion) -> bool:
    """
    Determine whether *candidate* is a meaningful upgrade over *current*,
    respecting the user's release channel.

    Rules:
    - The candidate's channel must be >= the current channel rank.
      (A stable user will never be told about a beta.)
    - The candidate must be strictly newer overall.
    """
    if candidate.channel_rank < current.channel_rank:
        return False
    return candidate > current


# ── GitHub Release Fetcher ───────────────────────────────────────────

GITHUB_API_URL = "https://api.github.com/repos/Mightyiest/TrueHour/releases"


@dataclass
class ReleaseInfo:
    """Lightweight container for a single GitHub release."""

    tag_name: str
    name: str
    html_url: str
    prerelease: bool
    draft: bool
    parsed: Optional[ParsedVersion] = field(default=None)


def _fetch_latest_releases() -> list[ReleaseInfo]:
    """
    Fetch the latest published releases from GitHub.
    Returns a list of ReleaseInfo sorted newest-first.
    Runs synchronously — should be called from a background thread.
    """
    import urllib.request
    import json

    req = urllib.request.Request(
        GITHUB_API_URL + "?per_page=15",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "TrueHour-UpdateChecker/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.debug(f"[UpdateChecker] Failed to fetch releases: {e}")
        return []

    if not isinstance(data, list):
        logger.debug(f"[UpdateChecker] GitHub API response is not a list: {data}")
        return []

    releases = []
    for item in data:
        if item.get("draft", False):
            continue
        tag = item.get("tag_name", "")
        parsed = parse_version(tag)
        if parsed is None:
            continue
        releases.append(
            ReleaseInfo(
                tag_name=tag,
                name=item.get("name", tag),
                html_url=item.get("html_url", ""),
                prerelease=item.get("prerelease", False),
                draft=False,
                parsed=parsed,
            )
        )

    # Sort newest first
    releases.sort(key=lambda r: r.parsed.sort_key, reverse=True)
    return releases


def find_best_upgrade(current_version_str: str) -> Optional[ReleaseInfo]:
    """
    Given the current version string, query GitHub and find the best
    upgrade candidate (if any) for the user's channel.
    """
    current = parse_version(current_version_str)
    if current is None:
        logger.warning(
            f"[UpdateChecker] Cannot parse current version: {current_version_str}"
        )
        return None

    releases = _fetch_latest_releases()
    for release in releases:
        if release.parsed and should_notify(current, release.parsed):
            return release

    return None


# ── Qt Signal Bridge (background thread → main thread) ───────────────


class UpdateCheckSignals(QObject):
    """Signals emitted by the background update check thread."""

    update_found = pyqtSignal(str, str)  # (new_version_display, release_url)
    no_update = pyqtSignal()
    check_failed = pyqtSignal(str)  # error message


def check_for_updates_async(current_version_str: str, signals: UpdateCheckSignals):
    """
    Run the update check in a background thread.
    Emits signals back to the main Qt thread.
    """

    def _worker():
        try:
            result = find_best_upgrade(current_version_str)
            if result and result.parsed:
                logger.info(
                    f"[UpdateChecker] Update available: {result.parsed.display} ({result.html_url})"
                )
                signals.update_found.emit(result.parsed.display, result.html_url)
            else:
                logger.info("[UpdateChecker] No update available.")
                signals.no_update.emit()
        except Exception as e:
            logger.warning(f"[UpdateChecker] Check failed: {e}")
            signals.check_failed.emit(str(e))

    thread = threading.Thread(target=_worker, daemon=True, name="UpdateChecker")
    thread.start()
