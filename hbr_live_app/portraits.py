"""Exact style-label lookup against the existing local portrait cache, no downloads."""
import sqlite3
from pathlib import Path


def portrait_path(label):
    if not label:
        return None
    try:
        from hbr_data.store import Catalog
        from hbr_data.assets import AssetStore
        catalog = Catalog()
        _, rows, _ = catalog.query("SELECT id FROM styles WHERE region='cn' AND label=?", (label,), limit=2)
        if len(rows) == 1:
            entry = AssetStore(catalog.root).get('cn', 'styles', rows[0][0])
            path = Path(entry['local_path']) if entry and entry.get('local_path') else None
            if path and path.is_file():
                return path
    except (OSError, ValueError, KeyError, sqlite3.Error):
        pass
    return None


class Portraits:
    def __init__(self, master):
        self.master = master
        self.cache = {}

    def get(self, label):
        if not label:
            return None
        if label not in self.cache:
            photo = None
            try:
                from PIL import Image, ImageTk
                path = portrait_path(label)
                if path:
                    with Image.open(path) as source:
                        picture = source.convert('RGBA')
                        picture.thumbnail((44, 44), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(picture, master=self.master)
            except (OSError, ValueError, KeyError, sqlite3.Error, ImportError):
                pass
            self.cache[label] = photo
        return self.cache[label]
