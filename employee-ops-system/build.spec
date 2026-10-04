# build.spec — PyInstaller spec for employee-ops-system
# Build with:  pyinstaller build.spec

import sys
import os
from pathlib import Path

block_cipher = None
APP_DIR = Path(SPECPATH) / "app"

a = Analysis(
    [str(Path(SPECPATH) / "app" / "main.py")],
    pathex=[SPECPATH],
    binaries=[],
    datas=[
        # Include Jinja2 templates and static assets inside the bundle
        (str(APP_DIR / "templates"), "app/templates"),
        (str(APP_DIR / "static"),    "app/static"),
        # Include Alembic migrations so the app can run them at startup
        (str(Path(SPECPATH) / "alembic"), "alembic"),
        (str(Path(SPECPATH) / "alembic.ini"), "."),
    ],
    hiddenimports=[
        "passlib.handlers.bcrypt",
        "sqlalchemy.dialects.sqlite",
        "alembic.runtime.migration",
        "alembic.script",
        "alembic.config",
        "aiofiles",
    ],
    hookspath=[],
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
    name="employee-ops-system",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,   # keep console window so errors are visible; set False for silent launch
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="employee-ops-system",
)
