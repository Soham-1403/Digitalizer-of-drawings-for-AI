# PyInstaller spec for building a standalone desktop executable.
#
# Usage (from the repo root, with the project's venv active):
#   pip install pyinstaller
#   pyinstaller packaging/pyinstaller.spec
#
# Output lands in dist/DigitalizerOfDrawings/ (onedir build — preferred
# over onefile for a PySide6 app: startup is faster and native library
# extraction issues are much easier to debug).

import sys
from pathlib import Path

block_cipher = None
project_root = Path(__file__).resolve().parent.parent

hidden_imports = [
    "engine",
    "engine.io",
    "engine.preprocess",
    "engine.vectorize",
    "engine.classify",
    "engine.confidence",
    "engine.cad",
    "engine.llm_assist",
    "engine.annotations",
    "engine.project",
    "app",
    "app.widgets",
    "app.tools",
    "PySide6.QtSvg",  # pulled in transitively by some Qt widget rendering paths
]

a = Analysis(
    [str(project_root / "app" / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DigitalizerOfDrawings",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="DigitalizerOfDrawings",
)
