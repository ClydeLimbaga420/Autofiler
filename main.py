"""
main.py

Windows File Explorer: hover over a file to see which formats it can be
converted to. Also adds "Convert to ..." right-click entries.

Run install/uninstall from an ADMIN terminal:
    python main.py install
    python main.py uninstall
    python main.py convert <file> <.ext>     (used by the right-click menu)
"""
import csv
import ctypes
import json
import os
import sys

# --------------------------------------------------------------------------
# Conversion map: source extension -> list of target extensions
# Edit this to add or remove formats.
# --------------------------------------------------------------------------
IMAGE_EXTS = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".ico", ".pdf"]

CONVERSIONS = {ext: [t for t in IMAGE_EXTS if t != ext] for ext in IMAGE_EXTS if ext != ".pdf"}
CONVERSIONS.update({
    ".csv": [".json"],
    ".json": [".csv"],
})

SUPPORTED_SOURCES = sorted(CONVERSIONS.keys())

MARKER = "FileConvertTip_Installed"
BACKUP = "FileConvertTip_Backup"


def tooltip_text(ext):
    pretty = ", ".join(t.lstrip(".").upper() for t in CONVERSIONS[ext])
    return f"Can convert to: {pretty}"


# --------------------------------------------------------------------------
# Converter
# --------------------------------------------------------------------------
def unique_path(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(f"{base} ({n}){ext}"):
        n += 1
    return f"{base} ({n}){ext}"


def convert(src, target_ext):
    src_ext = os.path.splitext(src)[1].lower()
    target_ext = target_ext.lower()
    dst = unique_path(os.path.splitext(src)[0] + target_ext)

    if src_ext in IMAGE_EXTS and target_ext in IMAGE_EXTS:
        from PIL import Image  # pip install pillow
        img = Image.open(src)
        if target_ext in (".jpg", ".jpeg", ".pdf", ".bmp") and img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        img.save(dst)

    elif src_ext == ".csv" and target_ext == ".json":
        with open(src, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)

    elif src_ext == ".json" and target_ext == ".csv":
        with open(src, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = [data]
        fields = []
        for row in data:
            for key in row:
                if key not in fields:
                    fields.append(key)
        with open(dst, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(data)

    else:
        raise ValueError(f"Cannot convert {src_ext} to {target_ext}")

    return dst


# --------------------------------------------------------------------------
# Install / uninstall (registry only, no COM needed)
# --------------------------------------------------------------------------
def _pythonw():
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        exe = exe[:-len("python.exe")] + "pythonw.exe"
    return exe


def _notify_shell():
    # SHCNE_ASSOCCHANGED = 0x08000000, SHCNF_IDLIST = 0
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)


def _keys_for(winreg, ext):
    """Registry keys that can hold InfoTip for this extension."""
    keys = [rf"SystemFileAssociations\{ext}"]
    try:
        progid = winreg.QueryValue(winreg.HKEY_CLASSES_ROOT, ext)
        if progid:
            keys.append(progid)
    except OSError:
        pass
    return keys


def _delete_tree(winreg, root, path):
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(winreg, root, rf"{path}\{sub}")
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        pass


def install():
    import winreg
    script = os.path.abspath(__file__)

    for ext in SUPPORTED_SOURCES:
        text = tooltip_text(ext)

        # Hover tooltip
        for key in _keys_for(winreg, ext):
            with winreg.CreateKeyEx(winreg.HKEY_CLASSES_ROOT, key, 0, winreg.KEY_ALL_ACCESS) as k:
                already_ours = False
                try:
                    winreg.QueryValueEx(k, MARKER)
                    already_ours = True
                except FileNotFoundError:
                    pass
                if not already_ours:
                    try:
                        old, _ = winreg.QueryValueEx(k, "InfoTip")
                        winreg.SetValueEx(k, BACKUP, 0, winreg.REG_SZ, old)
                    except FileNotFoundError:
                        pass
                winreg.SetValueEx(k, MARKER, 0, winreg.REG_SZ, "1")
                winreg.SetValueEx(k, "InfoTip", 0, winreg.REG_SZ, text)

        # Right-click "Convert to ..." entries
        base = rf"SystemFileAssociations\{ext}"
        for target in CONVERSIONS[ext]:
            verb = "ConvertTo" + target.lstrip(".").upper()
            with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, rf"{base}\shell\{verb}") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f"Convert to {target.lstrip('.').upper()}")
            with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, rf"{base}\shell\{verb}\command") as k:
                cmd = f'"{_pythonw()}" "{script}" convert "%1" {target}'
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)

    _notify_shell()
    print("Installed. Restart Explorer (or sign out/in) to see the tooltips.")


def uninstall():
    import winreg

    for ext in SUPPORTED_SOURCES:
        for key in _keys_for(winreg, ext):
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, key, 0, winreg.KEY_ALL_ACCESS) as k:
                    try:
                        winreg.QueryValueEx(k, MARKER)
                    except FileNotFoundError:
                        continue  # not installed by us
                    try:
                        old, _ = winreg.QueryValueEx(k, BACKUP)
                        winreg.SetValueEx(k, "InfoTip", 0, winreg.REG_SZ, old)
                        winreg.DeleteValue(k, BACKUP)
                    except FileNotFoundError:
                        try:
                            winreg.DeleteValue(k, "InfoTip")
                        except FileNotFoundError:
                            pass
                    winreg.DeleteValue(k, MARKER)
            except FileNotFoundError:
                pass

        base = rf"SystemFileAssociations\{ext}"
        for target in CONVERSIONS[ext]:
            verb = "ConvertTo" + target.lstrip(".").upper()
            _delete_tree(winreg, winreg.HKEY_CLASSES_ROOT, rf"{base}\shell\{verb}")

    _notify_shell()
    print("Uninstalled.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1].lower()
    if cmd == "install":
        install()
    elif cmd == "uninstall":
        uninstall()
    elif cmd == "convert" and len(sys.argv) == 4:
        try:
            out = convert(sys.argv[2], sys.argv[3])
            print(f"Created: {out}")
        except Exception as e:
            try:
                ctypes.windll.user32.MessageBoxW(0, str(e), "Conversion failed", 0x10)
            except Exception:
                pass
            print(f"Error: {e}")
            sys.exit(1)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()