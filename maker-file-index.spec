# PyInstaller spec for maker-file-index
# Build: pyinstaller maker-file-index.spec
#
# Produces a single self-contained executable in dist/.
# Must be built separately on each target platform:
#   macOS  -> dist/maker-file-index
#   Windows -> dist/maker-file-index.exe

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

block_cipher = None

# Bundle Jinja2 templates and dist-info metadata.
# copy_metadata is required so importlib.metadata.entry_points()
# can discover the plugins at runtime inside the frozen bundle.
datas = collect_data_files("maker_file_index")
datas += copy_metadata("maker-file-index")

a = Analysis(
    ["src/maker_file_index/cli.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # Plugins are loaded via entry_points() — PyInstaller can't detect them
        # automatically, so they must be listed here explicitly.
        "maker_file_index.plugins.lightburn",
        "maker_file_index.plugins.stl",
        "maker_file_index.plugins.scad",
        "maker_file_index.plugins.dxf",
        "maker_file_index.plugins.svg",
        "maker_file_index.plugins.three_mf",
        "maker_file_index.plugins.cdr",
        "maker_file_index.plugins.loader",
        # matplotlib — only the non-interactive Agg backend is needed
        "matplotlib.backends.backend_agg",
        # ezdxf drawing addon (DXF thumbnails)
        "ezdxf.addons.drawing",
        "ezdxf.addons.drawing.matplotlib",
        # numpy-stl (STL thumbnails)
        "stl",
        "stl.mesh",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy GUI backends we don't use
        "tkinter",
        "matplotlib.backends.backend_tkagg",
        "matplotlib.backends.backend_qt5agg",
        "matplotlib.backends.backend_wxagg",
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
    name="maker-file-index",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX compression disabled: can trigger antivirus false positives on Windows
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
