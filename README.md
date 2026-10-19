# File Convert Wheel (AUTOFILER)

Hover over a file in Windows File Explorer and a radial **wheel** pops up around your cursor. Each slice is a format the file can be converted to. Click a slice and the converted file is saved next to the original.

```
        PNG
   ICO       JPG
 TIFF   photo.. JPEG
   GIF       WEBP
        BMP
```

## Requirements

- Windows 10 or 11
- Python 3.9+ (the python.org installer, which includes Tk)
- Packages in `requirements.txt`:

```
pillow>=10.0.0
pywin32>=306
uiautomation>=2.0.18
```

## Install

```powershell
pip install -r requirements.txt
```

## Run the wheel

```powershell
python main.py wheel
```

Leave that window open, then rest your mouse on a file in File Explorer for about 0.7 seconds. Move the mouse away from the wheel (or press `Esc`) to dismiss it. Stop it with `Ctrl+C`.

Start it automatically when you sign in (no admin needed):

```powershell
python main.py startup
python main.py unstartup     # to remove
```

## Settings

Near the top of `main.py`:

```python
WHEEL_DWELL_MS = 700        # how long the mouse must rest on a file
WHEEL_REQUIRE_KEY = None    # None = hover only
                            # 0x10 = hold Shift, 0x11 = hold Ctrl, 0x12 = hold Alt
WHEEL_R_OUT = 150           # wheel size
```

If the wheel pops up too often, set `WHEEL_REQUIRE_KEY = 0x11` so it only appears while you hold Ctrl and hover.

## Supported conversions

| From | To |
|------|----|
| PNG, JPG, JPEG, WEBP, BMP, GIF, TIFF, ICO | any other image type above, or PDF |
| CSV | JSON |
| JSON | CSV (a list of objects, or one object) |

## Add your own formats

Edit the `CONVERSIONS` dict in `main.py`:

```python
CONVERSIONS.update({
    ".csv": [".json", ".xlsx"],
})
```

Then add a matching branch in `convert()` so the conversion actually works. The wheel resizes its slices automatically.

## Optional: tooltip text and right-click menu

Run from an **Administrator** terminal:

```powershell
python main.py install
python main.py uninstall
```

This adds plain hover text ("Can convert to: ...") and "Convert to ..." right-click entries. It is independent of the wheel.

## Command line

```powershell
python main.py convert "C:\pics\photo.png" .jpg
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Missing packages` | `pip install -r requirements.txt` |
| Wheel never appears | Hover over the file *name or icon* in a File Explorer window, and keep the mouse still. Desktop icons are not supported |
| Wheel appears on the wrong file | Two files with the same name but different hidden extensions (`a.png`, `a.jpg`) can be confused. Turn on *File name extensions* in the View menu |
| Wheel is slow in huge folders | The folder is scanned to find the file path; try a smaller folder |
| Nothing happens on click | Make sure Pillow is installed for the same Python, and that the output folder is writable |
| Doesn't work for an app running as admin | Run the wheel from an admin terminal too |

## Notes

- The wheel only reacts inside File Explorer windows, and only for the file types in `CONVERSIONS`.
- Existing files are never overwritten; ` (1)`, ` (2)` is added to the name instead.