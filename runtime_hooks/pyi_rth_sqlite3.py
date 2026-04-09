"""
Runtime hook for sqlite3 DLL loading
Adds the temp extraction directory to DLL search path
"""
import os
import sys

# Get the temp directory where PyInstaller extracts files
if hasattr(sys, '_MEIPASS'):
    # Add to DLL search path for Windows
    os.add_dll_directory(sys._MEIPASS)