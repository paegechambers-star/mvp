# PyInstaller-Spec für FraPP (Windows): FraPP + SCRIPTOR + G.O.D.A.I. Bauen: packaging\windows\build.ps1
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent.parent
PKG = ROOT / "scriptor"

datas = [
    (str(PKG / "config.yaml"), "scriptor"),
    (str(PKG / "genres"), "scriptor/genres"),
    (str(PKG / "app" / "static"), "scriptor/app/static"),
    (str(ROOT / "godai" / "config"), "godai/config"),
]
hiddenimports = (
    collect_submodules("scriptor")
    + collect_submodules("frapp")
    + collect_submodules("godai")
    + collect_submodules("uvicorn")
    + ["keyring.backends.Windows", "webview.platforms.edgechromium", "docx"]
)

a = Analysis(
    [str(Path(SPECPATH) / "frapp_app.py")],
    pathex=[str(ROOT), str(ROOT / "src")],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "numpy", "networkx"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="FraPP",
    console=False,
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="FraPP")
