"""Optional DXF -> DWG conversion.

There is no legitimate free/open-source way to *write* DWG directly —
it's Autodesk's proprietary binary format, and building or bundling an
unlicensed writer would put the firm at real legal risk. What we do
instead, honestly:

  - Always produce a real, standards-compliant, layered DXF (native).
  - If the free **ODA File Converter** (Open Design Alliance,
    https://www.opendesign.com/guestfiles/oda_file_converter) is
    installed locally, optionally shell out to it to produce a DWG
    alongside the DXF.
  - If it isn't installed, say so clearly in the UI rather than failing
    silently or pretending DWG was produced.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass


@dataclass
class DwgConversionResult:
    success: bool
    dwg_path: str | None
    message: str


def find_oda_file_converter() -> str | None:
    """Locate the ODA File Converter executable on this machine, if any."""
    for name in ("ODAFileConverter", "ODAFileConverter.exe", "oda_file_converter"):
        path = shutil.which(name)
        if path:
            return path

    common_paths = [
        "/usr/bin/ODAFileConverter",
        "/opt/ODAFileConverter/ODAFileConverter",
        r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe",
    ]
    for path in common_paths:
        if os.path.isfile(path):
            return path
    return None


def convert_dxf_to_dwg(
    dxf_path: str,
    out_dir: str,
    dwg_version: str = "ACAD2018",
    timeout_seconds: int = 60,
) -> DwgConversionResult:
    """Convert a DXF file to DWG using the ODA File Converter, if present.

    The converter operates on whole directories (its CLI contract), so we
    stage the single input file into an isolated temp folder and point it
    at that, then move the result into `out_dir`.
    """
    exe = find_oda_file_converter()
    if exe is None:
        return DwgConversionResult(
            success=False,
            dwg_path=None,
            message=(
                "ODA File Converter not found on this machine. DXF export "
                "succeeded and is fully usable in AutoCAD; install the free "
                "ODA File Converter to also produce a DWG."
            ),
        )

    os.makedirs(out_dir, exist_ok=True)
    with tempfile.TemporaryDirectory() as staging_in, tempfile.TemporaryDirectory() as staging_out:
        staged_input = os.path.join(staging_in, os.path.basename(dxf_path))
        shutil.copy(dxf_path, staged_input)

        # ODAFileConverter <in_dir> <out_dir> <out_version> <out_type> <recurse> <audit>
        cmd = [exe, staging_in, staging_out, dwg_version, "DWG", "0", "1"]
        try:
            subprocess.run(cmd, timeout=timeout_seconds, check=True, capture_output=True)
        except (subprocess.SubprocessError, OSError) as exc:
            return DwgConversionResult(success=False, dwg_path=None, message=f"ODA conversion failed: {exc}")

        produced = [f for f in os.listdir(staging_out) if f.lower().endswith(".dwg")]
        if not produced:
            return DwgConversionResult(
                success=False, dwg_path=None, message="ODA File Converter ran but produced no .dwg output."
            )

        final_path = os.path.join(out_dir, produced[0])
        shutil.move(os.path.join(staging_out, produced[0]), final_path)
        return DwgConversionResult(success=True, dwg_path=final_path, message="DWG conversion succeeded.")
