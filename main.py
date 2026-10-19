"""
main.py

Windows File Explorer: hover over a file and a radial "wheel" pops up around
the cursor showing the formats it can be converted to. Click a slice to convert.

Also supports (optional) a plain hover tooltip and right-click "Convert to ..."
entries.

Commands:
    python main.py wheel                run the hover wheel (leave it running)
    python main.py startup              start the wheel automatically at sign-in
    python main.py unstartup            remove the auto-start entry
    python main.py install              (admin) tooltip text + right-click entries
    python main.py uninstall            (admin) remove the above
    python main.py convert <file> <.ext>
"""
import csv
import ctypes
import json
import math
import os
import sys
import time

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

# --------------------------------------------------------------------------
# Wheel settings
# --------------------------------------------------------------------------
WHEEL_DWELL_MS = 700        # how long the mouse must rest on a file
WHEEL_REQUIRE_KEY = None    # None = hover only. Or 0x10 Shift, 0x11 Ctrl, 0x12 Alt (hold while hovering)
WHEEL_POLL_MS = 80
WHEEL_R_OUT = 150
WHEEL_R_IN = 55
WHEEL_TRANSPARENT = "#010101"
WHEEL_COLOR = "#2b2f3a"
WHEEL_COLOR_HOVER = "#4f7cff"
WHEEL_COLOR_CENTER = "#1b1e27"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "FileConvertWheel"


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
# Hover wheel
# --------------------------------------------------------------------------
class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _cursor_pos():
    pt = _POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _key_down(vk):
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


def _file_under_cursor(x, y):
    """Return the full path of the Explorer file under (x, y), or None."""
    import uiautomation as auto
    import win32com.client

    ctrl = auto.ControlFromPoint(x, y)
    item = ctrl
    for _ in range(4):
        if item is None:
            return None
        if item.ControlTypeName == "ListItemControl":
            break
        item = item.GetParentControl()
    else:
        return None
    if item is None or item.ControlTypeName != "ListItemControl":
        return None

    top = item.GetTopLevelControl()
    if top is None or top.ClassName != "CabinetWClass":
        return None
    hwnd = top.NativeWindowHandle
    name = item.Name

    shell_app = win32com.client.Dispatch("Shell.Application")
    for w in shell_app.Windows():
        try:
            if w.HWND != hwnd:
                continue
            folder = w.Document.Folder
            for it in folder.Items():
                if it.IsFolder:
                    continue
                if it.Name == name or os.path.basename(it.Path) == name:
                    return it.Path
        except Exception:
            continue
    return None


class ConvertWheel:
    """Borderless radial menu centred on the cursor."""

    def __init__(self, root, path, cx, cy, on_pick, on_close):
        import tkinter as tk
        self.tk = tk
        self.root = root
        self.path = path
        self.on_pick = on_pick
        self.on_close = on_close
        self.targets = CONVERSIONS[os.path.splitext(path)[1].lower()]
        self.step = 360.0 / len(self.targets)
        self.hover = -1
        self.closed = False

        self.size = WHEEL_R_OUT * 2 + 20
        self.c = self.size // 2
        self.screen_cx, self.screen_cy = cx, cy

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-transparentcolor", WHEEL_TRANSPARENT)
        self.win.configure(bg=WHEEL_TRANSPARENT)
        self.win.geometry(f"{self.size}x{self.size}+{cx - self.c}+{cy - self.c}")

        self.canvas = tk.Canvas(self.win, width=self.size, height=self.size,
                                bg=WHEEL_TRANSPARENT, highlightthickness=0)
        self.canvas.pack()

        self.arcs = []
        for i, target in enumerate(self.targets):
            start = 90 - (i + 1) * self.step
            arc = self.canvas.create_arc(
                self.c - WHEEL_R_OUT, self.c - WHEEL_R_OUT,
                self.c + WHEEL_R_OUT, self.c + WHEEL_R_OUT,
                start=start, extent=self.step, fill=WHEEL_COLOR,
                outline=WHEEL_COLOR_CENTER, width=2, style=tk.PIESLICE)
            self.arcs.append(arc)

        self.canvas.create_oval(self.c - WHEEL_R_IN, self.c - WHEEL_R_IN,
                                self.c + WHEEL_R_IN, self.c + WHEEL_R_IN,
                                fill=WHEEL_COLOR_CENTER, outline="")

        r_text = (WHEEL_R_OUT + WHEEL_R_IN) / 2
        for i, target in enumerate(self.targets):
            mid = math.radians((i + 0.5) * self.step)
            self.canvas.create_text(self.c + r_text * math.sin(mid),
                                    self.c - r_text * math.cos(mid),
                                    text=target.lstrip(".").upper(),
                                    fill="white", font=("Segoe UI", 10, "bold"))

        name = os.path.basename(path)
        if len(name) > 22:
            name = name[:19] + "..."
        self.canvas.create_text(self.c, self.c, text=name, fill="#cfd6e4",
                                width=WHEEL_R_IN * 1.6, font=("Segoe UI", 8), justify="center")

        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Button-1>", self._on_click)
        self.win.bind("<Escape>", lambda e: self.close())
        self.win.focus_force()
        self.win.after(WHEEL_POLL_MS, self._watch)

    def _hit(self, mx, my):
        dx, dy = mx - self.c, my - self.c
        r = math.hypot(dx, dy)
        if r < WHEEL_R_IN or r > WHEEL_R_OUT:
            return -1
        ang = math.degrees(math.atan2(dx, -dy)) % 360
        return min(int(ang // self.step), len(self.targets) - 1)

    def _on_motion(self, event):
        idx = self._hit(event.x, event.y)
        if idx != self.hover:
            if self.hover >= 0:
                self.canvas.itemconfig(self.arcs[self.hover], fill=WHEEL_COLOR)
            if idx >= 0:
                self.canvas.itemconfig(self.arcs[idx], fill=WHEEL_COLOR_HOVER)
            self.hover = idx

    def _on_click(self, event):
        idx = self._hit(event.x, event.y)
        self.close()
        if idx >= 0:
            self.on_pick(self.path, self.targets[idx])

    def _watch(self):
        if self.closed:
            return
        x, y = _cursor_pos()
        dist = math.hypot(x - self.screen_cx, y - self.screen_cy)
        if dist > WHEEL_R_OUT + 40:
            self.close()
            return
        self.win.after(WHEEL_POLL_MS, self._watch)

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.win.destroy()
        except Exception:
            pass
        self.on_close()


def _toast(root, text, x, y):
    import tkinter as tk
    t = tk.Toplevel(root)
    t.overrideredirect(True)
    t.attributes("-topmost", True)
    tk.Label(t, text=text, bg=WHEEL_COLOR_CENTER, fg="white",
             font=("Segoe UI", 10), padx=14, pady=8).pack()
    t.geometry(f"+{x + 12}+{y + 12}")
    t.after(2200, t.destroy)


def run_wheel():
    import tkinter as tk
    try:
        import uiautomation  # noqa: F401
        import win32com.client  # noqa: F401
    except ImportError:
        print("Missing packages. Run: pip install -r requirements.txt")
        sys.exit(1)

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

    root = tk.Tk()
    root.withdraw()
    state = {"pos": _cursor_pos(), "since": time.time(), "handled": False, "wheel": None}

    def on_close():
        state["wheel"] = None

    def on_pick(path, target):
        x, y = _cursor_pos()
        try:
            out = convert(path, target)
            _toast(root, f"Saved: {os.path.basename(out)}", x, y)
        except Exception as e:
            ctypes.windll.user32.MessageBoxW(0, str(e), "Conversion failed", 0x10)

    def tick():
        try:
            x, y = _cursor_pos()
            px, py = state["pos"]
            if abs(x - px) > 3 or abs(y - py) > 3:
                state["pos"] = (x, y)
                state["since"] = time.time()
                state["handled"] = False
            elif (state["wheel"] is None and not state["handled"]
                  and (time.time() - state["since"]) * 1000 >= WHEEL_DWELL_MS
                  and not _key_down(0x01)
                  and (WHEEL_REQUIRE_KEY is None or _key_down(WHEEL_REQUIRE_KEY))):
                state["handled"] = True
                path = _file_under_cursor(x, y)
                if path and os.path.splitext(path)[1].lower() in CONVERSIONS:
                    state["wheel"] = ConvertWheel(root, path, x, y, on_pick, on_close)
        except Exception as e:
            print(f"watcher error: {e}")
        root.after(WHEEL_POLL_MS, tick)

    print("Wheel running. Hover over a file in File Explorer. Ctrl+C to stop.")
    root.after(WHEEL_POLL_MS, tick)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass


# --------------------------------------------------------------------------
# Auto-start (current user, no admin needed)
# --------------------------------------------------------------------------
def _pythonw():
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        exe = exe[:-len("python.exe")] + "pythonw.exe"
    return exe


def startup():
    import winreg
    script = os.path.abspath(__file__)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, f'"{_pythonw()}" "{script}" wheel')
    print("The wheel will start automatically when you sign in.")


def unstartup():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, RUN_NAME)
    except FileNotFoundError:
        pass
    print("Auto-start removed.")


# --------------------------------------------------------------------------
# Install / uninstall (registry tooltip + right-click entries, needs admin)
# --------------------------------------------------------------------------
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
    if cmd == "wheel":
        run_wheel()
    elif cmd == "startup":
        startup()
    elif cmd == "unstartup":
        unstartup()
    elif cmd == "install":
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