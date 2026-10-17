"""Offline, bounded source verification; no installers, model calls, or services.

All scratch files and logs remain below this file's directory.
This is research tooling, not Ponytail or TokenMaster production code.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent
SOURCE = BASE / "source/ponytail-c982cd411abb53323c4baa1baa3c2f020b8d0b08"
SCRATCH = BASE / "verification-scratch"
LOGS = BASE / "verification"
for directory in (SCRATCH, LOGS):
    directory.mkdir(exist_ok=True)

env = {k: v for k, v in os.environ.items()
       if k.upper() in ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")}
for key in ("TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "APPDATA",
            "LOCALAPPDATA", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR"):
    target = SCRATCH / key.lower()
    target.mkdir(exist_ok=True)
    env[key] = str(target)
env.update(PONYTAIL_DEFAULT_MODE="full", PYTHONDONTWRITEBYTECODE="1",
           PYTHONIOENCODING="utf-8")
node = shutil.which("node")
assert node
results = []


def run(name, command, stdin=None, extra_env=None):
    proc = subprocess.run(command, cwd=SOURCE, env={**env, **(extra_env or {})},
                          input=stdin, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)
    (LOGS / f"{name}.stdout.txt").write_text(proc.stdout, encoding="utf-8")
    (LOGS / f"{name}.stderr.txt").write_text(proc.stderr, encoding="utf-8")
    result = {"name": name, "command": command, "exit_code": proc.returncode,
              "stdout": f"verification/{name}.stdout.txt",
              "stderr": f"verification/{name}.stderr.txt"}
    results.append(result)
    print(name, "exit", proc.returncode)
    print(proc.stdout[-1000:])
    if proc.stderr:
        print(proc.stderr[-1000:])
    return proc


run("node-selected", [node, "--test",
    "tests/behavior.test.js", "tests/hooks-windows.test.js",
    "ponytail-mcp/test/instructions.test.js",
    "ponytail-mcp/test/server.test.js"])
run("loc-regressions", [node, "benchmarks/loc.test.js"])
run("correctness-regressions", [node, "benchmarks/correctness.test.js"])
run("version-consistency", [node, "scripts/check-versions.js"])
run("rule-consistency", [node, "scripts/check-rule-copies.js"])
run("completeness-gate-offline",
    [sys.executable, "-B", "benchmarks/agentic/complete.py", "--selftest-offline"])

# Deliberately do not call run.py --selftest: it also exercises a Node HTTP
# server and a process-tree killer. Only the ten reviewed pure Python task
# scorers below are executed against upstream's fixed good/bad references.
scorer_script = r"""
import json, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path('benchmarks/agentic').resolve()))
from tasks import TASKS
names = ['safe-path','rate-limit','sql-user','auth-token','csv-sum','cache',
         'critic-email','trace-transfer','reuse-slug','reuse-money']
rows=[]
for name in names:
    task=TASKS[name]
    for kind in ('good','bad'):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            for fn,content in task.get('seed',{}).items():
                (root/fn).write_text(content,encoding='utf-8')
            (root/task['file']).write_text(task[kind],encoding='utf-8')
            result=task['score'](root)
        axis=task.get('axis','safe')
        passed=(result['correct']==1 and result['safe']==1) if kind=='good' else result[axis]==0
        rows.append(dict(task=name,reference=kind,passed=passed,result=result))
print(json.dumps(rows,indent=2))
assert all(r['passed'] for r in rows)
"""
run("agentic-10-scorers", [sys.executable, "-B", "-c", scorer_script])

# A direct activation/tracker probe with a private Codex-style data directory.
# It proves state and context mechanics, not model compliance or host loading.
runtime_script = r"""
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
const env={...process.env,PLUGIN_DATA:process.env.PROBE_STATE,
  CLAUDE_PLUGIN_ROOT:process.cwd(),CLAUDE_PROJECT_DIR:'C:/research/project-A'};
const state=path.join(env.PLUGIN_DATA,'ponytail-modes','C__research_project-A');
function hook(file,payload){
 const r=cp.spawnSync(process.execPath,[path.join('hooks',file)],
 {env,input:JSON.stringify(payload),encoding:'utf8',timeout:5000});
 if(r.status!==0) throw Error(r.stderr);
 return r.stdout ? JSON.parse(r.stdout) : {};
}
const rows=[];
rows.push({step:'startup',output:hook('ponytail-activate.js',{source:'startup'})});
if(fs.readFileSync(state,'utf8')!=='full')throw Error('startup not full');
rows.push({step:'switch-ultra',output:hook('ponytail-mode-tracker.js',{prompt:'/ponytail ultra'})});
if(fs.readFileSync(state,'utf8')!=='ultra')throw Error('switch not ultra');
rows.push({step:'review-one-shot',output:hook('ponytail-mode-tracker.js',{prompt:'/ponytail-review'})});
if(fs.readFileSync(state,'utf8')!=='ultra')throw Error('review changed mode');
rows.push({step:'compact',output:hook('ponytail-activate.js',{source:'compact'})});
if(fs.readFileSync(state,'utf8')!=='full')throw Error('compact did not reset to default');
rows.push({step:'stop',output:hook('ponytail-mode-tracker.js',{prompt:'stop ponytail'})});
if(fs.existsSync(state))throw Error('stop did not clear state');
rows.push({step:'resume',output:hook('ponytail-activate.js',{source:'resume'})});
if(fs.readFileSync(state,'utf8')!=='full')throw Error('resume did not reset to default');
for(const r of rows){
 const o=r.output.hookSpecificOutput;
 r.event=o?.hookEventName;
 r.context_header=o?.additionalContext?.split('\n')[0] || null;
 delete r.output;
}
console.log(JSON.stringify(rows,null,2));
"""
run("runtime-state-probe", [node, "-e", runtime_script],
    extra_env={"PROBE_STATE": str(SCRATCH / "codex-data")})

tree = json.loads((BASE / "upstream-tree.json").read_text(encoding="utf-8-sig"))
hashes = []
for entry in tree["tree"]:
    if entry["type"] != "blob":
        continue
    data = (SOURCE / entry["path"]).read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    hashes.append({"path": entry["path"], "verified": actual == entry["sha"],
                   "sha256": hashlib.sha256(data).hexdigest()})
assert all(row["verified"] for row in hashes)
summary = {"date": "2026-10-04", "node": subprocess.check_output([node, "--version"], text=True).strip(),
           "python": sys.version.split()[0], "platform": sys.platform,
           "upstream_blobs_verified": len(hashes), "commands": results,
           "all_commands_passed": all(r["exit_code"] == 0 for r in results),
           "limitations": [
               "No model benchmarks, API calls, services, installers, or host plugin installation.",
               "No full npm test: selected tests only; full hooks.test.js assumes /bin/sh.",
               "No MCP stdio handshake; MCP tests are instruction selection and source-wiring checks.",
               "No run.py full selftest (contains HTTP service and tree-kill exercises)."]}
(BASE / "verification-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
