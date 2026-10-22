"""Small process-local caches invalidated by SQLite commits, including other processes."""
from collections import OrderedDict
from copy import deepcopy
from functools import wraps
import sqlite3
from threading import RLock
from weakref import finalize
from .config import database_path


def versioned_read(function):
    entries=OrderedDict();lock=RLock()
    @wraps(function)
    def read(path=None):
        target=(path or database_path()).resolve();identity=(str(target),target.stat().st_ino)
        with lock:
            entry=entries.get(identity)
            if entry is None:
                connection=sqlite3.connect(target.as_uri()+'?mode=ro',uri=True,check_same_thread=False)
                connection.execute('PRAGMA query_only=ON')
                entry={'connection':connection,'version':None,'value':None};entries[identity]=entry
            entries.move_to_end(identity)
            while len(entries)>8:
                _,old=entries.popitem(last=False);old['connection'].close()
            connection=entry['connection'];version=connection.execute('PRAGMA data_version').fetchone()[0]
            if entry['version']==version:return deepcopy(entry['value'])
            result=function(path)
            if connection.execute('PRAGMA data_version').fetchone()[0]==version:
                entry.update(version=version,value=deepcopy(result))
            return result
    def close_entries():
        with lock:
            for entry in entries.values():entry['connection'].close()
            entries.clear()
    finalize(read,close_entries)
    return read
