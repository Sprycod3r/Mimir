# -*- mode: python ; coding: utf-8 -*-
#
# Mimir.spec — PyInstaller build spec
#
# Produces a FOLDER distribution (--onedir) for fast startup.
# Output: dist/Mimir/Mimir.exe + dist/Mimir/_internal/
#
# Build command: pyinstaller Mimir.spec
# (Run from the launcher/ directory with venv active)

import os
from pathlib import Path

src_dir = os.path.join(os.getcwd(), 'src')

# PyQt6-WebEngine requires its helper process (QtWebEngineProcess.exe) and
# resource files to be collected alongside the main exe.
try:
    from PyInstaller.utils.hooks import collect_data_files as _cdf
    _webengine_datas = _cdf('PyQt6.QtWebEngineCore')
except Exception:
    _webengine_datas = []

# bcrypt and cryptography have native components; collect_all ensures
# their DLLs and data files are bundled correctly.
try:
    from PyInstaller.utils.hooks import collect_all as _ca
    _bcrypt_d, _bcrypt_b, _bcrypt_h = _ca('bcrypt')
    _crypto_d, _crypto_b, _crypto_h = _ca('cryptography')
except Exception:
    _bcrypt_d = _bcrypt_b = _bcrypt_h = []
    _crypto_d = _crypto_b = _crypto_h = []

a = Analysis(
    [os.path.join(src_dir, 'main.py')],
    pathex=[src_dir],
    binaries=[
        *_bcrypt_b,
        *_crypto_b,
    ],
    datas=[
        # Bundle config files alongside the exe
        ('config', 'config'),
        # Bundle theme assets
        ('assets', 'assets'),
        # WebEngine resource files (empty list if PyQt6-WebEngine not installed)
        *_webengine_datas,
        *_bcrypt_d,
        *_crypto_d,
    ],
    hiddenimports=[
        'psutil',
        'psutil._pswindows',
        'PyQt6.QtCore',
        'PyQt6.QtWidgets',
        'PyQt6.QtGui',
        # WebEngine — optional; MediaPanel falls back gracefully if absent
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebEngineCore',
        # Security — bcrypt and cryptography
        *_bcrypt_h,
        *_crypto_h,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim unused Qt modules to reduce exe size
        'PyQt6.QtMultimedia',
        'matplotlib',
        'numpy',
        'PIL',
        'tkinter',
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Mimir',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX compression sometimes triggers AV false positives — leave off
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='assets/mimir.ico',  # Uncomment when icon is added
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Mimir',
)
