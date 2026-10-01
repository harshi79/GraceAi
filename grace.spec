# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build for the Aero Grace desktop client.

Build (one file, windowed, no console):

    pyinstaller --noconfirm --clean grace.spec

The result is written to ``dist/Grace`` (Linux/macOS) or ``dist\\Grace.exe``
(Windows).
"""

import os
import sys

block_cipher = None

HERE = os.path.abspath(os.path.dirname(__file__))

a = Analysis(
    [os.path.join(HERE, "run.py")],
    pathex=[HERE],
    binaries=[],
    datas=[],
    hiddenimports=[
        "grace",
        "grace.config",
        "grace.models",
        "grace.errors",
        "grace.logutil",
        "grace.modes",
        "grace.sse",
        "grace.client",
        "grace.controller",
        "grace.attachments",
        "grace.markdown_render",
        "grace.ui",
        "grace.ui.theme",
        "grace.ui.widgets",
        "grace.ui.markdown_view",
        "grace.ui.chat_view",
        "grace.ui.composer",
        "grace.ui.sidebar",
        "grace.ui.login_view",
        "grace.ui.app",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "numpy",
        "pandas",
        "PyQt5",
        "PySide6",
        "matplotlib",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Grace",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
