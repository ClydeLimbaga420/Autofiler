# File Convert Tooltip (AUTOFILER)

Hover over a file in Windows File Explorer and a tooltip shows which formats it can be converted to. Right-click entries ("Convert to PNG", etc.) run the actual conversion.

```
Can convert to: JPG, JPEG, WEBP, BMP, GIF, TIFF, ICO, PDF
```

It works by writing standard Explorer registry values (`InfoTip` and right-click verbs), so there is no background process and no COM server.

## Requirements

- Windows 10 or 11
- Python 3.9+
- An **administrator** terminal for install/uninstall
- Packages in `requirements.txt`:

```
pillow>=10.0.0
```

## Install

Open **PowerShell as Administrator** in the project folder:

```powershell
pip install -r requirements.txt
python main.py install
```

Then restart Explorer:

```powershell
taskkill /f /im explorer.exe; start explorer.exe
```

## Usage

- **Hover** over a supported file to see the tooltip.
- **Right-click** the file (on Windows 11: *Show more options*) and pick **Convert to ...**.
- The converted file is saved next to the original. Existing files are never overwritten; a ` (1)`, ` (2)` suffix is added instead.

Convert from the command line (what the menu calls):

```powershell
python main.py convert "C:\pics\photo.png" .jpg
```

## Supported conversions

| From | To |
|------|----|
| PNG, JPG, JPEG, WEBP, BMP, GIF, TIFF, ICO | any other image type above, or PDF |
| CSV | JSON |
| JSON | CSV (a list of objects, or one object) |

## Add your own formats

Edit the `CONVERSIONS` dict near the top of `main.py`:

```python
CONVERSIONS.update({
    ".csv": [".json", ".xlsx"],   # list what the tooltip should show
})
```

Then add a matching branch in `convert()` so the conversion actually works, and re-run:

```powershell
python main.py uninstall
python main.py install
```

## Uninstall

```powershell
python main.py uninstall
```

Any `InfoTip` value that existed before install is restored.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `PermissionError` / access denied on install | Run the terminal as Administrator |
| No tooltip appears | Restart Explorer, and make sure Folder Options > View > **Show pop-up description for folder and desktop items** is ticked |
| Tooltip shows something else | That file type uses its own tooltip rules; the text is set on both the extension's association key and its ProgID |
| Menu entry does nothing | Check that `pythonw.exe` sits next to `python.exe` and Pillow is installed for that same Python |
| Moved the script | Uninstall, move it, then install again (menu commands store the script path) |

## Notes

- The tooltip text is the same for every file of a type, because it is a fixed registry string. It does not include the file name.
- Tooltips are based on file extension only, not file contents.