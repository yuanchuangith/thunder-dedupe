# PyInstaller hook for sqlite3
# Ensures sqlite3.dll is properly bundled
import os
import sys
from pathlib import Path

def get_conda_library_bin():
    """Find conda Library/bin directory"""
    python_dir = Path(sys.executable).parent

    # Check common conda locations
    candidates = [
        python_dir / "Library" / "bin",
        python_dir.parent / "Library" / "bin",
        Path("D:/Anaconda/envs/checkcode/Library/bin"),
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None

binaries = []
lib_bin = get_conda_library_bin()

if lib_bin:
    # Add sqlite3.dll to the package root
    sqlite_dll = lib_bin / "sqlite3.dll"
    if sqlite_dll.exists():
        binaries.append((str(sqlite_dll), "."))

    # Also add other required DLLs
    dll_names = ["liblzma.dll", "LIBBZ2.dll", "libmpdec-4.dll", "libexpat.dll", "ffi.dll"]
    for dll_name in dll_names:
        dll_path = lib_bin / dll_name
        if dll_path.exists():
            binaries.append((str(dll_path), "."))