# Offline authoring evidence — structure preprotection

Status: **not prepared, not executed; parent review/release outstanding**.
Only this new qualifier directory was authored. No production or old qualifier,
run, audit, corpus/prompt/gold/registry or resource file was changed.

## Source basis and boundaries

Read the parent implementation contract and current finalized worker API. The
public API probe and independent worker review are context, not inferred native
qualification. No native executable, Docker, model, neural compressor, provider
socket, dependency installer, or preparation command was invoked here.

The old qualifier's 10-file inventory is retained in `ORIGIN.json` and tested
unchanged. Copied failure-rendering fixture provenance stays unchanged.
Exact snapshots of the existing pure parser/guard:

| Source | SHA256 |
|---|---|
| document_structure.py | 5925a75902a07fd9c585516d99240f79896d877f11251a6899f730649d7001f4 |
| protected_text.py | 4406825058e81b7c76c3d2ecfc4de76d08e4636d9ad950b6c7a51c1c4444136f |

The snapshots are only stdlib grammar/fence checking; no runtime/worker/model
import. Independent typed receipts, hashes, pristine slices and native wire
checks supplement the shared grammar. This is not an independent Markdown
grammar implementation, blind evaluation or semantic-quality oracle.

## Fresh test runs

Working directory: `C:\Users\shyamsridhar\code\TokenMaster`.

```powershell
$q='evidence/integrated-runtime-20261009/structure-preprotection/qualifier'
$old=$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
try {
  python -I -B -m pytest -q --tb=short -p no:cacheprovider --noconftest -c "$q/pytest.ini" "$q"
  $code=$LASTEXITCODE
} finally {
  $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD=$old
}
```

1. First integrated authoring run: **1 failed, 204 passed in 1.53s**, exit 1.
   Missing worker recovery reply raised KeyError rather than the deliberate
   fail-closed ValueError expected by the inherited regression. Added the
   explicit response-presence check; did not weaken the assertion.
2. After that repair: **205 passed in 0.66s**, exit 0.
3. After additional cumulative-count/publication/raw-envelope/cancellation and
   unchanged-configuration regressions: **215 passed in 0.90s**, exit 0.

Scope includes inherited Root/action-schema/native failure/MCP/typed-JSON/wire/
interruption/persistence/non-restart tests plus new preprotection contract,
span completeness/digests, table/list/fence integrity, generated-frame leakage,
raw fragment/source bindings, count separation and no candidate-publication
credit. Synthetic receipts are explicitly checker-only fixtures; no token or
compression measurement was taken.

Installed Ruff was queried with:
`python -I -B -c "import importlib.util; print('ruff_available',importlib.util.find_spec('ruff') is not None)"`.
Output: `ruff_available False`. No linter/dependency was installed. A separate
package build target does not exist for this standalone stdlib qualifier.

## Remaining limits / stop condition

No new output directory, freeze, install, native or neural qualification has been
created. The actual route may reject spans, fail framing/raw-fragment validation,
produce a no-op, expand the complete wire, or fail native recovery/cleanup.
All such outcomes must remain failures; the exact cell is not dropped.

Only the first emitted fragment is actively requested under the fixed budget;
all native-published handles require validation evidence. Public store reads
intentionally affect feedback and are not treated as free or as model recovery.
Internal annotation digests/counts are worker attestations, not independently
captured neural inputs. Pure parser reuse and source pinning do not prove
surrounding prose semantics, query coverage, model quality or efficiency.

Next step belongs to the parent: complete independent worker review, review
these new authoring files, supply a fresh isolated current installation, freeze
the explicit new plan, then authorize its one-shot capped execution.
