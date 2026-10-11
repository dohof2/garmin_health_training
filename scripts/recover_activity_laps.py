"""Recover FIT lap metadata from preserved originals; never reimport samples."""
import io
import json
import zipfile
from pathlib import Path
from app.database import connect
from app.activity_metrics import preserve_fit_summary
from app.fit_import import _decode_fit
from app.sync import _fit_content


def recover(path=None):
    with connect(path) as c:
        rows=c.execute("""SELECT a.id,s.stored_path FROM fit_import_files f
            JOIN activities a ON a.id=f.activity_id JOIN source_files s ON s.id=f.fit_source_file_id
            WHERE f.status='completed' AND a.fit_detail_version<2 AND a.deleted_at IS NULL AND a.source_name!='synthetic_fixture'""").fetchall()
        live=c.execute("""SELECT a.id,s.stored_path FROM activities a JOIN source_files s
            ON s.original_name IN ('activity-'||a.source_record_id||'.fit','activity-'||a.source_record_id||'.zip')
            WHERE a.fit_detail_version<2 AND a.deleted_at IS NULL AND a.source_name!='synthetic_fixture'""").fetchall()
    groups={};direct=[]
    for row in [*rows,*live]:
        parts=(row['stored_path'] or '').split('!/')
        if len(parts)==3:groups.setdefault((parts[0],parts[1]),[]).append((row['id'],parts[2]))
        elif len(parts)==1:direct.append((row['id'],parts[0]))
    stats={'recovered':0,'failed':0,'laps':0};seen=set()
    def save(identifier,content):
        if identifier in seen:return
        messages,errors=_decode_fit(content)
        if errors:raise ValueError('FIT decoding failed')
        with connect(path) as c:preserve_fit_summary(c,identifier,messages)
        seen.add(identifier);stats['recovered']+=1;stats['laps']+=len(messages.get('lap_mesgs') or [])
        if stats['recovered']%100==0:print(json.dumps(stats),flush=True)
    for (outer_name,nested_name),members in groups.items():
        try:
            with zipfile.ZipFile(outer_name) as outer:
                with zipfile.ZipFile(io.BytesIO(outer.read(nested_name))) as nested:
                    for identifier,member in members:
                        try:save(identifier,nested.read(member))
                        except (ValueError,OSError,KeyError,zipfile.BadZipFile):stats['failed']+=1
        except (OSError,KeyError,zipfile.BadZipFile):stats['failed']+=len(members)
    for identifier,filename in direct:
        try:save(identifier,_fit_content(Path(filename).read_bytes()))
        except (ValueError,OSError,zipfile.BadZipFile):stats['failed']+=1
    return stats


if __name__=='__main__':print(json.dumps(recover()),flush=True)
