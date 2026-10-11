"""Archival ZIP bundling for a packaged run.

The bundle is the single file a user hands to someone else: the manifest, the
product document in both Markdown and HTML, the run log, and every JSON
artifact.

Two properties are enforced rather than assumed:

* **Reproducible bytes.** Entry order is sorted, every entry carries a fixed
  DOS timestamp and fixed Unix mode, and ``create_system`` is pinned, so the
  archive layout and per-entry metadata are identical across platforms and
  runs. The compressed bytes are fixed for a given zlib implementation, so
  two runs with the same inputs produce a byte-identical archive on the same
  platform/Python build (across OSes the deflate stream may differ with the
  zlib version, which is outside this module's control).
* **No self-inclusion.** The archive is assembled from an explicit member
  list, so ``<run_id>.zip`` can safely live inside the directory it packages.
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Final

__all__ = ["build_run_bundle"]

#: The DOS epoch. Used for every entry so the archive carries no wall clock.
_FIXED_DATE_TIME: Final = (1980, 1, 1, 0, 0, 0)
_FIXED_CREATE_SYSTEM: Final = 3  # Unix, independent of the building host.
_FIXED_EXTERNAL_ATTR: Final = 0o644 << 16


def build_run_bundle(
    *,
    root: Path,
    run_id: str,
    members: Iterable[tuple[str, Path]],
) -> Path:
    """Write ``<root>/<run_id>.zip`` from ``members`` and return its path.

    ``members`` pairs the archive-relative name with the file on disk. They
    are written in sorted archive-name order so the same inputs always yield
    the same archive.
    """
    bundle = root / f"{run_id}.zip"
    ordered = sorted(members, key=lambda member: member[0])

    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for archive_name, path in ordered:
            info = zipfile.ZipInfo(archive_name, date_time=_FIXED_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = _FIXED_CREATE_SYSTEM
            info.external_attr = _FIXED_EXTERNAL_ATTR
            archive.writestr(info, path.read_bytes())

    return bundle
