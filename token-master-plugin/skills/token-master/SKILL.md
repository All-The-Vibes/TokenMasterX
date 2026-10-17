---
name: token-master
description: Configure graph navigation and conservative token-efficiency tools for an explicitly selected host. Use when the user asks to enable TokenMaster, graph routing, recoverable views, or scoped token-efficiency discipline. Not a universal interceptor or a task-quality guarantee.
---

# TokenMaster

Use the smallest requested surface. An informational or explain-only request does
not authorize repository edits or a host installation. Preserve requested depth,
proofs, safety checks and justified reusable abstractions.

## Graph navigation setup

Run the script from this skill directory with the requested repository, explicit
host and an already provisioned pinned runtime:

```text
<runtime-python> setup.py <repo-root> --host claude|codex|copilot --python <runtime-python>
```

The script requires an already installed graph supplier. Do not install an
unverified similarly named package or silently resolve dependencies at every
launch. Optional supplier installation is a separate explicit choice. Runtime
pins are in the plugin's `requirements-runtime.txt` and closure lock.

Report the actual installer result, not a claim that a host accepted a tool.
Claude/Copilot get a routing agent; Codex gets native MCP configuration, not a
translated Claude agent or output-replacement hook. Honor the restart guidance
printed for the selected host. Never rewrite another host's profile by guessing.

Treat graph output as candidate locations. Check index/source freshness, follow
bounded pages until the required enumeration is complete, and verify decisive
edges in source. `semantic_complete=false` is not an exhaustive dependency proof.
Freshness covers indexed files, not newly added unindexed files.

## Recoverable views

The model-invoked `brainspace_compress` tool defaults to conservative behavior.
Explicit navigation may expose code skeletons; explicit overview may sample
suitable structured content. Exact/edit/debug/aggregate/exhaustive/security tasks
must retain their answer-bearing material. Errors and mixed media pass through.

Use `brainspace_retrieve(ref, offset, limit)` repeatedly at `next_offset` until
`complete=true`. Verify digests when reconstructing originals. Exact search is
available via `brainspace_search`; a bounded snippet is not the full original.
Do not treat a stored original, a shorter view, or a Jev confidence as proof of
successful task completion.

MCP is model-invoked, not transparent interception. The Claude PostToolUse adapter
has a separate versioned schema and runtime-acceptance gate. Unknown hosts/shapes
are not assumed compatible. No model-visible savings footer is required.

## Scoped discipline

For an explicitly requested task-local mode, state a compact contract:

1. Required result.
2. Non-goals.
3. Evidence needed.
4. Stop condition.
5. Optional advisory output-token budget, without suppressing requested detail.

`brainspace_tools.py` exposes task-local and explicit session-keyed modes. Never
infer that an enable flag from another session applies here. `off` removes only
this mode's owned state; it does not delete unrelated configuration or claim to
erase instructions already in a conversation. The review-only companion is
`token-master-review` and does not authorize edits.

## Evaluation and improvement

Use the token-only reference metric: all observed model inputs and outputs across
the whole task, including failures, retries, auxiliary decisions and recovery.
Keep learning separate; reject partial or nonmaterialized traces rather than
inventing totals. Native counters are diagnostics, not interchangeable units.

`token_efficiency.py` exposes the durable controller and an offline synthetic
fixture. The fixture verifies plumbing, not real language-model performance.
The installed `session` runtime can explicitly select actual pinned Ponytail
instructions and Headroom. `initialize-runtime` / `learn-runtime` connect a
bounded real read-only evaluator; initialization is safety admission only, and
learning compares an enabled local incumbent with a local neighbor, not an
optimizer-off baseline. See `docs/PRODUCT_RUNTIME.md` before using these paths.
For full compositions, `initialize-profile` / `learn-profile` use closed
`RuntimePolicy` data and explicit pinned resources, with a true-off default.
They reuse the strict registry/evaluator and do not promote automatically.
See `docs/PROFILE_LEARNING.md`; Jev abstention is not an improvement judgment.
Opt-in V4 adds lexical JSON payload compaction with exact original recovery;
it is not sampling or a default change. See `docs/LEXICAL_JSON_POLICY.md` and
`docs/LEXICAL_JSON_RESULTS.md` for its presentation contract and limited evidence.
The optional `--require-nonexpanding-input` session guard includes composition
overhead and falls back to the exact original input; it is not a task-savings
or quality certificate and is not enabled globally.
It may omit newly inserted optional guidance while retaining a valid smaller
context; reports distinguish configured and applied instructions. Headroom's
optional `--headroom-time-budget-seconds` is explicit, bounded and profile-bound,
not a hard wall-time guarantee or permission to forward arbitrary environment.
Real candidates need an independent outcome evaluator, fresh confirmation data,
a fixed measurement/regime, valid whole-task bounds and the persisted promotion
gate. Jev is optional advisory screening, network-disabled unless explicitly
configured; never send repository data or secrets as an implicit side effect.

See the plugin's `docs/TOKEN_EFFICIENCY.md` and `docs/IMPLEMENTATION_PLAN.md` for
the proof assumptions, supported boundaries and remaining release qualification.
