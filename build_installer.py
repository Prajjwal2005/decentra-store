#!/usr/bin/env python3
"""
Build script for DecentraStore Node Installer

Creates a standalone Windows executable from node_installer_gui.py

Requirements:
    pip install pyinstaller

Usage:
    python build_installer.py

Output:
    dist/DecentraStore-Installer.exe (ready to distribute)
"""

import subprocess
import sys
import os
from pathlib import Path


def check_pyinstaller():
    """Check if PyInstaller is installed."""
    try:
        import PyInstaller
        print(f"✅ PyInstaller {PyInstaller.__version__} found")
        return True
    except ImportError:
        print("❌ PyInstaller not found")
        print("\nInstalling PyInstaller...")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "pyinstaller"],
                check=True
            )
            print("✅ PyInstaller installed successfully")
            return True
        except Exception as e:
            print(f"❌ Failed to install PyInstaller: {e}")
            return False


def build_installer():
    """Build the installer executable."""
    print("\n" + "="*60)
    print("Building DecentraStore Node Installer")
    print("="*60 + "\n")

    # Check PyInstaller
    if not check_pyinstaller():
        return False

    # Build command
    cmd = [
        "pyinstaller",
        "--onefile",  # Single executable
        "--windowed",  # No console window
        "--name", "DecentraStore-Installer",  # Output name
        "--icon=NONE",  # No icon (you can add one later)
        "node_installer_gui.py"
    ]

    print("Running PyInstaller...")
    print(f"Command: {' '.join(cmd)}\n")

    try:
        result = subprocess.run(cmd, check=True)

        print("\n" + "="*60)
        print("✅ Build successful!")
        print("="*60)

        exe_path = Path("dist") / "DecentraStore-Installer.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"\nExecutable: {exe_path}")
            print(f"Size: {size_mb:.2f} MB")
            print("\nYou can now distribute this file to Windows users.")
            print("They just need to download and run it - no dependencies required!")
        else:
            print("\n⚠️  Executable not found at expected location")

        return True

    except subprocess.CalledProcessError as e:
        print(f"\n❌ Build failed: {e}")
        return False


def clean_build_files():
    """Clean up build artifacts."""
    import shutil

    print("\nCleaning up build artifacts...")

    dirs_to_remove = ["build", "dist", "__pycache__"]
    files_to_remove = ["DecentraStore-Installer.spec"]

    for d in dirs_to_remove:
        if Path(d).exists():
            shutil.rmtree(d)
            print(f"  Removed: {d}/")

    for f in files_to_remove:
        if Path(f).exists():
            Path(f).unlink()
            print(f"  Removed: {f}")


def main():
    """Main build process."""
    import argparse

    parser = argparse.ArgumentParser(description="Build DecentraStore Node Installer")
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts")
    args = parser.parse_args()

    if args.clean:
        clean_build_files()
        print("\n✅ Cleanup complete")
        return

    # Build
    success = build_installer()

    if success:
        print("\n" + "="*60)
        print("Next steps:")
        print("="*60)
        print("1. Test the installer: dist/DecentraStore-Installer.exe")
        print("2. Upload to your website for users to download")
        print("3. Or distribute via GitHub releases")
        print("\nTo clean build files: python build_installer.py --clean")
        sys.exit(0)
    else:
        print("\n❌ Build failed - check errors above")
        sys.exit(1)


if __name__ == "__main__":
    main()
