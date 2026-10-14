"""Optional local catalog enrichment, cached outside the UI thread."""
import sqlite3


class Names:
    def __init__(self):
        self.cache = {}

    def actor(self, label):
        return self.lookup(label)[0]

    def style(self, label):
        return self.lookup(label)[1]

    def lookup(self, label):
        if label not in self.cache:
            result = label or '未知角色'
            style = ''
            try:
                from hbr_data.store import Catalog
                _, rows, _ = Catalog().query(
                    "SELECT json_extract(raw_json,'$.chara'), name FROM styles WHERE region='cn' AND label=?",
                    (label,), limit=1)
                if rows and rows[0][0]:
                    result = rows[0][0].split(' — ')[0].split(' · ')[0].strip()
                if rows:
                    style = rows[0][1] or ''
            except (OSError, ValueError, RuntimeError, sqlite3.Error):
                pass
            self.cache[label] = (result, style)
        return self.cache[label]
