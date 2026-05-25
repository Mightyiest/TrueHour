"""
FocusLog — Version Information.
Single source of truth for version and build metadata.
"""

from dataclasses import dataclass

<<<<<<< Updated upstream
__version__ = "2.0.2"
=======
<<<<<<< Updated upstream
__version__ = "2.0.1"
=======
__version__ = "2.0.5"
>>>>>>> Stashed changes
>>>>>>> Stashed changes

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

<<<<<<< Updated upstream
INFO = VersionInfo(version=__version__, build_date="2026.05.24", build_number=8)
=======
<<<<<<< Updated upstream
INFO = VersionInfo(version=__version__, build_date="2026.05.23", build_number=7)
=======
INFO = VersionInfo(version=__version__, build_date="2026.05.26", build_number=10)
>>>>>>> Stashed changes
>>>>>>> Stashed changes
VERSION_SHORT = INFO.short
VERSION_FULL = INFO.full
