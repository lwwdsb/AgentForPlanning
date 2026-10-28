"""SQLite authority: short transactions, immutable events, derived exports."""
from contextlib import contextmanager
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3

from .domain import Run, dumps

SCHEMA = '''
CREATE TABLE IF NOT EXISTS requests(request_id TEXT PRIMARY KEY, run_id TEXT UNIQUE NOT NULL,
 fingerprint TEXT NOT NULL, snapshot TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(run_id TEXT NOT NULL, sequence INTEGER NOT NULL, body TEXT NOT NULL,
 PRIMARY KEY(run_id,sequence));
CREATE TABLE IF NOT EXISTS ledger(attempt_id TEXT PRIMARY KEY, request_id TEXT NOT NULL,
 amount_minor INTEGER NOT NULL CHECK(amount_minor>0), body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS artifacts(artifact_id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
 body TEXT NOT NULL);
'''


class Store:
    def __init__(self, path, readonly=False):
        self.path = str(Path(path).resolve())
        if readonly:
            self.db = sqlite3.connect(Path(self.path).as_uri() + '?mode=ro', uri=True)
        else:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(self.path, timeout=5)
            self.db.executescript(SCHEMA)
        self.db.row_factory = sqlite3.Row

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def get(self, request_id):
        row = self.db.execute('SELECT snapshot FROM requests WHERE request_id=?', (request_id,)).fetchone()
        return None if row is None else Run.from_dict(json.loads(row['snapshot']))

    def claim(self, run):
        with self.transaction():
            existing = self.get(run.request.request_id)
            if existing is not None:
                return existing, False
            self.db.execute('INSERT INTO requests VALUES(?,?,?,?)',
                            (run.request.request_id, run.run_id, run.request.fingerprint, dumps(asdict(run))))
        return run, True

    def commit(self, run, events=(), ledger=None, artifact=None, before_commit=None):
        with self.transaction():
            if ledger:
                self.db.execute('INSERT INTO ledger VALUES(?,?,?,?)',
                                (ledger['attempt_id'], run.request.request_id, ledger['amount_minor'], dumps(ledger)))
            if artifact:
                self.db.execute('INSERT INTO artifacts VALUES(?,?,?)',
                                (artifact['artifact_id'], run.request.request_id, dumps(artifact)))
            seq = self.db.execute('SELECT COALESCE(MAX(sequence),0) FROM events WHERE run_id=?', (run.run_id,)).fetchone()[0]
            for event in events:
                seq += 1
                body = {'schema_version':'1.0.0', 'run_id':run.run_id, 'request_id':run.request.request_id,
                        'sequence':seq, 'round':run.rounds_used, 'mode':run.request.mode,
                        'timestamp':run.effective_now, **event}
                self.db.execute('INSERT INTO events VALUES(?,?,?)', (run.run_id, seq, dumps(body)))
            self.db.execute('UPDATE requests SET snapshot=? WHERE request_id=?',
                            (dumps(asdict(run)), run.request.request_id))
            if before_commit:
                before_commit()

    def snapshot(self, request_id):
        # Deferred read transaction gives all views one consistent database snapshot.
        self.db.execute('BEGIN')
        try:
            run = self.get(request_id)
            if run is None: raise KeyError('not_found')
            events = [json.loads(r[0]) for r in self.db.execute(
                'SELECT body FROM events WHERE run_id=? ORDER BY sequence', (run.run_id,))]
            row = self.db.execute('SELECT body FROM artifacts WHERE request_id=?', (request_id,)).fetchone()
            return run, events, None if row is None else json.loads(row[0])
        finally:
            self.db.rollback()

    def recover(self, request_id):
        import os
        import socket
        from .domain import Clock, iso
        with self.transaction():
            run=self.get(request_id)
            if run is None:raise KeyError('not_found')
            if run.status!='running':return run.result
            if run.owner_host!=socket.gethostname() or run.owner_pid<=0:
                raise ValueError('owner cannot be confirmed dead')
            try:
                os.kill(run.owner_pid,0)
            except ProcessLookupError:
                pass
            except (PermissionError,OSError):
                raise ValueError('owner cannot be confirmed dead') from None
            else:
                raise ValueError('owner still alive')
            run.status='incomplete';run.reason_code='interrupted'
            run.remaining_work=['运行已中断；保留已提交成果，使用新请求重新规划']
            for a in run.attempts:
                if a['status']=='running':a.update(status='failed',quality='none',error='interrupted')
            for step in run.steps:
                if step['status']=='running':step['status']='failed'
            run.result.update(status=run.status,reason_code=run.reason_code,remaining_work=run.remaining_work,
                              steps=run.steps,attempts=run.attempts)
            seq=self.db.execute('SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE run_id=?',(run.run_id,)).fetchone()[0]
            event={'schema_version':'1.0.0','run_id':run.run_id,'request_id':request_id,'sequence':seq,
                   'round':run.rounds_used,'timestamp':iso(Clock().now_utc()),'mode':run.request.mode,
                   'event_type':'terminal','payload':{'status':'incomplete','reason_code':'interrupted'}}
            self.db.execute('INSERT INTO events VALUES(?,?,?)',(run.run_id,seq,dumps(event)))
            self.db.execute('UPDATE requests SET snapshot=? WHERE request_id=?',(dumps(asdict(run)),request_id))
        return run.result


def export_evidence(snapshot, destination):
    """Export derived files; DB remains untouched. Manifest hashes detect partial bundles."""
    import hashlib
    import os
    from uuid import uuid4
    run, events, artifact = snapshot
    dest=Path(destination)
    dest.mkdir(parents=True,exist_ok=True)
    files={'input.json':dumps(run.request.raw_input)+'\n',
           'output.json':dumps(run.result)+'\n',
           'trace.jsonl':''.join(dumps(event)+'\n' for event in events)}
    if artifact: files['artifact.json']=dumps(artifact)+'\n'
    manifest={'schema_version':'1.0.0','request_id':run.request.request_id,'run_id':run.run_id,
              'mode':run.request.mode,'status':run.status,'final_snapshot':run.status!='running',
              'started_at':run.started_at,'logical_now':run.logical_now,
              'execution_config':run.request.execution_config,'rules_digest':run.request.rules_digest,
              'material_digest':run.request.material_digest,'config_digest':run.request.config_digest,
              'files':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in files.items()},
              'evidence_scope':'offline_flow_only' if run.request.mode=='mock' else 'actual_model_run'}
    files['manifest.json']=dumps(manifest)+'\n'
    for name,content in files.items():
        tmp=dest/(name+'.'+uuid4().hex+'.tmp')
        try:
            tmp.write_text(content,encoding='utf-8')
            os.replace(tmp,dest/name)
        finally:
            tmp.unlink(missing_ok=True)
    if not artifact: (dest/'artifact.json').unlink(missing_ok=True)
