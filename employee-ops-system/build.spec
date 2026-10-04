# build.spec — PyInstaller spec for employee-ops-system (single-file exe)
# Build with:  pyinstaller build.spec
# Output:      dist/employee-ops-system.exe
#
# Set CONSOLE = False for the end-user build (no console window; output goes to
# ops-system.log next to the exe). Keep True while testing so errors are visible.

from pathlib import Path

CONSOLE = False

block_cipher = None
APP_DIR = Path(SPECPATH) / "app"

a = Analysis(
    [str(Path(SPECPATH) / "app" / "main.py")],
    pathex=[SPECPATH],
    binaries=[],
    datas=[
        # Jinja2 templates, static assets (incl. vendor/htmx + chart.js), and Alembic files
        (str(APP_DIR / "templates"), "app/templates"),
        (str(APP_DIR / "static"),    "app/static"),
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
        # uvicorn picks its loop/protocol implementations by name at runtime
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Single file: binaries, zipfiles and datas are packed INTO the exe (no COLLECT step).
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="employee-ops-system",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX-packed exes are a common antivirus false-positive
    runtime_tmpdir=None,
    console=CONSOLE,
    disable_windowed_traceback=False,
    icon=None,
)
