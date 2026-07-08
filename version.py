"""
TrueHour - Version Information.
Single source of truth for version and build metadata.
"""

from dataclasses import dataclass

__version__ = "3.3.3-beta.2"


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
        return f"v{self.version} \u00b7 Build {self.build_date}"


INFO = VersionInfo(version=__version__, build_date="2026.07.04", build_number=34)
VERSION_SHORT = INFO.short
VERSION_FULL = INFO.full
