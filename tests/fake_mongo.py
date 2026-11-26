"""測試用的迷你 MongoDB：只實作這個專案用到的查詢，讓 API 測試不需要真的資料庫。

用法：
    import fake_mongo; fake_mongo.install()   # 必須在 create_app() 之前
"""
import copy
import itertools
from types import SimpleNamespace

_ids = itertools.count(1)


def _match(doc, query):
    for k, want in query.items():
        if k == '$or':
            if not any(_match(doc, q) for q in want):
                return False
        elif doc.get(k) != want:
            return False
    return True


class Cursor(list):
    def sort(self, field, direction=1):
        return Cursor(sorted(self, key=lambda d: d.get(field), reverse=direction < 0))


class Collection:
    def __init__(self):
        self.docs = []

    def find_one(self, query):
        return next((copy.deepcopy(d) for d in self.docs if _match(d, query)), None)

    def find(self, query=None, projection=None):
        out = []
        for d in self.docs:
            if _match(d, query or {}):
                d = copy.deepcopy(d)
                for k, keep in (projection or {}).items():
                    if not keep:
                        d.pop(k, None)
                out.append(d)
        return Cursor(out)

    def insert_one(self, doc):
        doc = copy.deepcopy(doc)
        doc.setdefault('_id', next(_ids))
        self.docs.append(doc)
        return SimpleNamespace(inserted_id=doc['_id'])

    def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if _match(d, query):
                d.update(copy.deepcopy(update.get('$set', {})))
                return SimpleNamespace(matched_count=1, upserted_id=None)
        if upsert:
            doc = {k: v for k, v in query.items() if not k.startswith('$')}
            doc.update(update.get('$set', {}))
            doc.update(update.get('$setOnInsert', {}))
            self.insert_one(doc)
            return SimpleNamespace(matched_count=0, upserted_id=doc.get('_id'))
        return SimpleNamespace(matched_count=0, upserted_id=None)

    def delete_one(self, query):
        for i, d in enumerate(self.docs):
            if _match(d, query):
                del self.docs[i]
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)

    def delete_many(self, query):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _match(d, query)]
        return SimpleNamespace(deleted_count=before - len(self.docs))


def install():
    """把 server.db 裡的三個資料表換成記憶體版本，回傳 (users, history, friends)。"""
    from server import db
    db.users_col, db.history_col, db.friends_col = Collection(), Collection(), Collection()
    return db.users_col, db.history_col, db.friends_col
