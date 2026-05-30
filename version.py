"""
TrueHour — Version Information.
Single source of truth for version and build metadata.
"""

from dataclasses import dataclass

__version__ = "3.0.0"

@dataclass(frozen=True)
class VersionInfo:
    version: str
    build_date: str
    build_number: int

    @property
    def short(self) -> str:
        return f"v{self.version}"

    @property
    def full(self) -> str:
        return f"v{self.version} · Build {self.build_date}"

INFO = VersionInfo(version=__version__, build_date="2026.05.30", build_number=16)
VERSION_SHORT = INFO.short
VERSION_FULL = INFO.full
