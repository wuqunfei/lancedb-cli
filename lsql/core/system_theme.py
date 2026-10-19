"""Best-effort detection of the OS/terminal's light-vs-dark preference, used only to
pick a sensible default theme on launch. Always falls back to dark on any failure —
there's no reliable cross-platform/cross-terminal way to know for sure."""

import subprocess
import sys


def system_prefers_dark() -> bool:
    try:
        if sys.platform == "darwin":
            return _macos_prefers_dark()
        if sys.platform == "win32":
            return _windows_prefers_dark()
        return _linux_prefers_dark()
    except Exception:
        return True


def _macos_prefers_dark() -> bool:
    result = subprocess.run(
        ["defaults", "read", "-g", "AppleInterfaceStyle"],
        capture_output=True,
        text=True,
        timeout=1,
    )
    return result.returncode == 0 and "dark" in result.stdout.strip().lower()


def _windows_prefers_dark() -> bool:
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return value == 0


def _linux_prefers_dark() -> bool:
    result = subprocess.run(
        ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
        capture_output=True,
        text=True,
        timeout=1,
    )
    if result.returncode == 0:
        return "dark" in result.stdout.strip().lower()
    return True
