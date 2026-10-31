# Proofs of TokenMaster's core claims

This folder states the invariants behind TokenMaster's mechanisms as theorems and proves them in
Lean 4 (4.35.0, core library only, no Mathlib). Lean's kernel checks every proof. No proof uses
`sorry`, and none relies on an axiom beyond Lean's standard three (`propext`, `Classical.choice`,
`Quot.sound`).

A Lean proof is about a model of the code, not about the Python itself. Each model takes what it
needs from the code as explicit hypotheses. Some hypotheses are checked by
[`test_proof_conformance.py`](../token-master-plugin/skills/token-master/tests/test_proof_conformance.py),
on generated inputs and on the recorded study data; the rest are assumptions. The table under
"What the proofs assume" says which is which. Each test's docstring names the theorems it supports,
and tests named `test_finding_*` reproduce the gaps listed under "Findings".

The headline numbers (about half the tokens, the same pass rate) are measurements, not theorems.
What can be proven is how the mechanisms behind them behave, and which properties the measurement
definitions have. Section 7 covers the method.

## Summary

| Claim | Status | Main theorems |
| --- | --- | --- |
| The BYOK bridge never changes bytes the provider already cached | Proven, under the assumptions in section 1 | `Cache.bridge_prefix_stable`, `Cache.cache_prefix_kept` |
| With policy v6 and no guidance, the runtime never changes an earlier message | Proven for the shaping map, which `plan_request` keeps, and the runtime keeps unless shaping would pass a `max_input_tokens` cap (section 2) | `Cache.shaping_prefix_stable` |
| Shaping never makes a tool result bigger, in tokens or in bytes | Proven | `Shaping.guard_never_expands` |
| `plan_request` with policies v1 to v4 never grows a request or touches a protected message | Proven | `Policy.greedy_never_expands`, `Policy.protected_unchanged` |
| The `rg` and glob folds are lossless | Proven: `fold_paths` gives back its exact input, and `fold_search` refuses any input it could not give back (section 3) | `Folds.unfoldPaths_foldPaths`, `Folds.unfold_foldSearchChecked` |
| Routing drops only auxiliary tools, and keeps every family whose trigger fires | Proven; the triggers miss some phrasings (finding 2) | `Routing.excluded_subset_lean`, `Routing.fired_family_kept` |
| A resume that the launcher ties to the session's record gets the `--excluded-tools` the session started with | Proven for the model; which record applies is the launcher's lookup, which the conformance tests check (section 4) | `Routing.resume_same_list`, `Routing.resume_chain_keeps_first_list` |
| Sessions whose system prompts differ only in the folder path get the same system prompt | Proven | `SessionPrefix.system_same_across_sessions` |
| Navigation results stay under 2,400 tokens | Proven, in the navigation server's counter: every result is measured whole and cut to fit (section 6) | `NavCap.assemble_le` |
| The measurement definitions have the properties the protocol relies on | Proven; `analyze.py`'s outputs match them on the recorded data; the interval's coverage is assumed | `Measurement.resample_within_task_range` |

## How to check

Install Lean with [elan](https://github.com/leanprover/elan), then build. `lake` reads the pinned
version from `lean-toolchain`.

```bash
cd proofs && lake build
```

The conformance tests run with the plugin's test suite:

```bash
cd token-master-plugin/skills/token-master && python -m pytest tests/test_proof_conformance.py
```

To list the axioms a theorem depends on, run `lake env lean` on a file that imports
`TokenMasterProofs` and contains, for example, `#print axioms TokenMasterProofs.Cache.bridge_prefix_stable`.

## What the proofs assume

| Hypothesis | Used by | Status |
| --- | --- | --- |
| `shape_tool_result` depends only on the tool name, the arguments and the output | sections 1, 2 | Holds by reading the code: it reads nothing else, and the counter is fixed for a session. The tests only show that it gives the same output twice |
| A new item never reuses a call id the earlier history mentions | sections 1, 2 | Assumed: Copilot CLI gives every call a new id |
| The client sends the same instructions and tool list on every call of a session | section 1 | Assumed. The test fixture builds them equal, so it cannot check the client. A resume that the launcher ties to the session's record passes the recorded `--excluded-tools` again (section 4), and given the same list, Copilot CLI 1.0.105 sent the same tools and the earlier input on a resume in one probe (`evidence/session-tools-20261030`). Other resumes, and `--all-tools` or `TOKENMASTER_KEEP_TOOLS` on a resume, may change the list |
| The provider's cached prefix puts the instructions and the tool list before the items | section 1 | Assumed. Anthropic documents the order tools, system, messages; Theorem 3 needs only both before the items |
| The token counter never raises | section 1 | False for a lone surrogate (finding 1) |
| A request's bytes are a fixed part plus each content's escaped size | section 2 | Follows from how `json.dumps` writes a string; not tested |
| A prompt's billed tokens are a fixed part plus a count of each message's decoded text, and that count falls whenever the message's cl100k count falls | section 2 | Assumed: providers bill the decoded text with their own tokenizers, and how they join messages is not published. `test_v6_plans_keep_earlier_messages` checks the cl100k side: the tool messages' text never grows, and shrinks whenever a plan changes something |
| `plan_request` with v1 to v4 never edits a protected position | section 2 | Checked for v1 by `test_plan_request_never_expands_and_keeps_protected_messages`. v6 shapes every tool result, which Theorem 1 shows keeps the cache |
| A printed directory head is never indented, never a notice, and never `.` itself | section 3 | Not indented: checked, as `test_fold_paths_round_trip` adds entries that start with spaces, which `_PATH` must make `fold_paths` refuse. Never a notice and never `.`: hold by reading the code, since a printed head ends in a separator or is `.` |
| An owning path is never itself an entry line, and an owned line has digits and a `:` or `-` | section 3 | Checked: `test_fold_search_round_trip` adds match lines whose path looks like an entry. With `_SUSPECT_PATH`'s whitespace rules removed, the test fails |
| No copied search line looks like a folded entry | section 3 | Guaranteed by the code: `fold_search` refuses such input (Theorem 11) |
| The model's tool families are the code's | section 4 | Checked: `test_routing_lists_match_the_lean_model` |
| The folder path has no newline and no surrounding whitespace | section 5 | No newline by the regular expression; whitespace is stripped (finding 3) |
| The empty text fits the budget | section 6 | Holds for both the exact count and the fallback estimate, which count it as 0 |
| A cache write never costs less than a cache read | section 7 | Checked: `test_cache_writes_never_cost_less_than_reads`, on the one price pair the recorded calls have |

## 1. The bridge keeps the provider's cache valid

Source: `rewrite_request` in `brainspace_copilot_bridge.py`. Lean: `TokenMasterProofs/Cache.lean`.

Copilot CLI resends the whole history on every call, and the provider caches exact prompt prefixes.
A call reads the earlier part of its prompt from the cache only if that part is byte-identical to
what an earlier call sent. The bridge rewrites every request in two ways: it moves the session
folder line from the system prompt into the first user message (section 5), and it shapes each tool
output using the name and arguments of the call with the same id.

The model. A history $h$ is a list of items: `call(i, name, args)`, `output(i, body)`, `user(text)`
or `other`. Let $L_h(i)$ be the last call in $h$ with id $i$; Python keeps the calls in a dict, so
the last one wins. The shaping map is

```math
S(h) = \operatorname{map}\bigl(s_{L_h}\bigr)(h),
\qquad
s_L(\mathtt{output}(i, b)) =
\begin{cases}
\mathtt{output}(i, \mathit{shape}(n, a, b)) & \text{if } L(i) = (n, a)\\
\mathtt{output}(i, b) & \text{otherwise,}
\end{cases}
```

and $s_L$ leaves every other item alone. Here $\mathit{shape}$ is `shape_tool_result` with the
session's token counter, extended by the identity for tools of kind "other" and for unreadable
arguments: a function of the tool name, the arguments and the output, and of nothing else. The
bridge is $B(h) = S(P(h))$, where $P$ prepends the folder header to the first user item.

**Theorem 1** (`Cache.shaping_prefix_stable`). If no call in $e$ has an id that an item of $h$
mentions, then $S(h)$ is a prefix of $S(h \mathbin{+\!\!+} e)$.

*Proof.* $S(h \mathbin{+\!\!+} e)$ is $\operatorname{map}(s_{L'})(h) \mathbin{+\!\!+} \operatorname{map}(s_{L'})(e)$
with $L' = L_{h \mathbin{+\!\!+} e}$. Take an output item $\mathtt{output}(i, b)$ of $h$. By
hypothesis $e$ contains no call with id $i$, so the calls with id $i$ in $h \mathbin{+\!\!+} e$ are
exactly those in $h$, $L'(i) = L_h(i)$, and the item is shaped as in $S(h)$. $s$ leaves every other
item unchanged. The first part therefore equals $S(h)$. ∎

**Theorem 2** (`Cache.bridge_prefix_stable`). If $h$ also contains a user item, $B(h)$ is a prefix of
$B(h \mathbin{+\!\!+} e)$.

*Proof.* $P$ changes only the first user item, which lies in $h$, so
$P(h \mathbin{+\!\!+} e) = P(h) \mathbin{+\!\!+} e$. $P$ changes no id, so the hypothesis of Theorem 1
holds for $P(h)$ and $e$, and Theorem 1 gives the result. ∎

**Theorem 3** (`Cache.cache_prefix_kept`). Serialize a request as a header $H$ (the instructions and
the tool list), then the first item's encoding, then a comma and the encoding of each later item.
If $H$ is the same on both calls, the serialization of $B(h)$ is a prefix of the serialization of
$B(h \mathbin{+\!\!+} e)$.

*Proof.* By Theorem 2, $B(h \mathbin{+\!\!+} e) = B(h) \mathbin{+\!\!+} t$ for some $t$. The
encoding of a later item does not depend on the items after it, so the encoding of
$B(h) \mathbin{+\!\!+} t$ is the encoding of $B(h)$ followed by the encodings of $t$. ∎

Every byte the provider cached for the previous call, up to the end of its last item, is sent again
unchanged, provided the assumptions in the table above hold: unique call ids, the same instructions
and tools on every call, a counter that does not raise, and a provider whose cached prefix puts the
instructions and tools before the items. The provider matches tokens rather than bytes, so the last
few tokens before new content can differ when the tokenizer splits the text differently at the
boundary.

`test_bridge_rewrite_keeps_history_prefix` runs `rewrite_request` over an 8-call session with
search, glob and view results. On every call the rewritten input starts with the previous call's,
and the JSON of the previous input, without its closing bracket, is a prefix of the next.

## 2. Shaping never makes a result bigger, and v6 never changes an earlier message

Source: `shape_tool_result` and `plan_v6_request` in `brainspace/v6_shaping.py`, `plan_request` in
`brainspace/request_policy.py`, and `_prepare` in `brainspace/runtime.py`. Lean:
`TokenMasterProofs/Shaping.lean`, `TokenMasterProofs/Policy.lean` and `TokenMasterProofs/Cache.lean`.

`shape_tool_result` ends with a guard (line 280). Given the original $o$ and a candidate $c$, it
returns

```math
G(o, c) =
\begin{cases}
c & \text{if } c \ne o,\ \mathit{count}(c) < \mathit{count}(o) \text{ and } \mathit{wire}(c) \le \mathit{wire}(o)\\
o & \text{otherwise,}
\end{cases}
```

where `count` is the cl100k count of the decoded text, the text a provider bills with its own
tokenizer, and `wire` is the size in bytes of the JSON-escaped string the request carries.
Everything before the guard only produces the candidate, so the model needs only the guard.

**Theorem 4** (`Shaping.guard_never_expands`, `Shaping.guard_strict_if_changed`). $G$ has no more
tokens and no more bytes than $o$, and if $G \ne o$ it has strictly fewer tokens. *Proof:* by cases
on the condition. ∎

**Theorem 5** (`Shaping.request_bytes_never_grow`). If a request's bytes are a fixed part $k$ plus
each content's escaped size, shaping every tool result never adds bytes:

```math
k + \sum_j \mathit{wire}(G(o_j, c_j)) \le k + \sum_j \mathit{wire}(o_j).
```

*Proof:* term by term, by Theorem 4. ∎

**Theorem 6** (`Shaping.billed_tokens_shrink_if_additive`). If a prompt's tokens are a fixed part
plus each content's count, shaping that changes at least one result lowers them strictly. Under the
billing assumption in the table above, the provider's bill falls too.
*Proof:* every term is at most its original, and one is strictly smaller. ∎

`plan_v6_request` (`plan_request` with policy v6, the native runtime's default) applies the shaping
map $S$ of section 1 to a chat request's tool messages, with the calls looked up by id in a dict.
Before this change it then measured the whole request on the JSON wire and reverted the whole plan
when that count was not smaller. On the wire a newline or a backslash takes two characters, so a
fold that saved tokens on the decoded text could measure no smaller there, and it was reverted with every other
message of the request, earlier ones included; the call missed the cached prefix. The glob output
`C:\work\repo\lib.rs`, `C:\work\repo\util.py`, `tests/data.json` went from 21 to 19 tokens and stayed
at 23 on the wire, and was reverted. The runtime made the same comparison twice more, in its final
wire guard and in its composition step.

Now none of the three places reverts v6 shaping on the whole request's token count; the byte checks
stay, and by Theorem 5 they cannot fire. Theorem 1 then says each v6 plan starts with the previous
plan's messages: no earlier message changes. A v6 request can measure more tokens on the wire than
the original, while its decoded text, which is what the provider bills, has fewer cl100k tokens
(Theorem 6). Three cases keep the old behavior. With a guidance message inserted, which
`RuntimePolicy` rejects for v6 because it shifts every later message, the runtime applies its usual
non-expanding guard. It applies the same guard when the shaped request would exceed a
`max_input_tokens` cap, so it sends the unshaped request if that fits instead of failing the call;
that call changes earlier messages. And `plan_request` still returns a request unchanged when its
envelope is invalid or the counter fails; the runtime rejects such requests before planning.

`test_v6_plans_keep_earlier_messages` checks 240 v6 plans over 40 growing sessions: each starts with
the previous plan's messages, and the tool messages' decoded text never grows and shrinks whenever a
plan changes something. `test_runtime_keeps_v6_shaping` gives the runtime a v6 plan whose request
has fewer bytes and more tokens, and checks that it is kept, and that with a cap at the original's
count the original is sent instead. `test_v6_keeps_a_fold_that_saves_raw_tokens`
checks the glob output above: fewer tokens, no fewer on the wire, kept.
`test_v6_shapes_regardless_of_stable_prefix` shows that v6 shapes messages the stable prefix covers,
which Theorem 1 shows is safe for the cache.

`plan_request` with policies v1 to v4 walks the eligible tool results in order and accepts a
proposal only if it has strictly fewer tokens and no more bytes than the request as it stands
(lines 511, 561 and 624). It stops after `max_transforms` acceptances; v4 stops after that many
attempts, which also bounds the acceptances. The model takes the edits as functions on a request
and the measure as a function, so it covers every transform the code can call.

**Theorem 7** (`Policy.greedy_never_expands`, `Policy.greedy_strict`, `Policy.greedy_count_le`). The
plan never has more tokens or bytes than the original request; if any edit was accepted it has
strictly fewer tokens; at most `max_transforms` edits are accepted.

*Proof.* By induction on the list of edits. An accepted edit lowers the tokens and does not raise the
bytes, and by induction the rest of the run raises neither. Each acceptance adds one to the count,
and the loop stops when the count reaches `max_transforms`. ∎

**Theorem 8** (`Policy.protected_unchanged`, `Policy.metadata_unchanged`). Accepted edits only set a
message's content. If no edit's position is protected, every protected message is exactly the
original, and no message's role, ids, tool calls or other fields change.

*Proof.* By induction on the edits: setting the content at position $i$ leaves every position
$j \ne i$ unchanged, and keeps the metadata at $i$. ∎

For v1 to v4 the code's eligibility test supplies Theorem 8's hypothesis: it skips the first
`stable_prefix_messages` messages, the caller's exact-answer indices, the newest
`keep_recent_tool_results` tool results and every non-tool message.
`test_plan_request_never_expands_and_keeps_protected_messages` checks Theorems 7 and 8 on 300 random
v1 requests, some with proposals longer than the original so that the reject branch runs.
`test_shaped_results_never_expand` checks Theorem 4 on 75 search, glob, view and other results, and
that ranged reads and error results are never changed.

## 3. The folds are lossless

Source: `fold_paths` and `fold_search` in `brainspace/v6_shaping.py`. Lean:
`TokenMasterProofs/Folds.lean`.

The model works on lines. It takes the Python's classification as given (which lines are path
entries, which file owns a search line) and states as hypotheses what that classification must
guarantee.

`fold_paths` splits each path at its last separator into a head and a name, prints the head when it
changes (`.` for an empty head), then the name indented by two spaces, then the `[...]` notices and
the input's trailing newlines. It refuses an empty line inside the list, so an empty line in its
output can only be a trailing one. Its inverse treats an indented line as a name under the current
head, passes empty lines and notices through, and reads any other line as a new head, `.` meaning
the empty head.

**Theorem 9** (`Folds.unfoldPaths_foldPaths`). If no printed head is indented or a notice, and no head
is `.` itself, unfolding gives back every path, every notice and every trailing empty line, in order:

```math
\mathit{unfold}\bigl(\mathit{fold}(es) \mathbin{+\!\!+} ts\bigr) = \operatorname{map}(\mathit{head} \mathbin{+\!\!+} \mathit{name})(es) \mathbin{+\!\!+} ts.
```

*Proof.* By induction on the entries, carrying the current head. When the head is unchanged, the
fold prints only the indented name, and the inverse appends it to the current head. When the head
changes, the fold prints the head line first; the inverse reads it as a head, since it is neither
indented, empty nor a notice, and maps it back to the head (`.` to the empty head, which is
unambiguous because no head is `.`). The tail lines pass through. ∎

At the text level, unfolding gives back the input exactly, trailing newlines included.

`fold_search` prints one header per file, then each owned line `path{sep}{num}{sep}{text}` as
`  {num}{sep} {text}`, and copies every line no file owns. If a copied line looks like such an entry,
it refuses to fold. Its inverse rebuilds an entry under the current header, reads a non-entry line
as a header when an entry follows it, and copies it otherwise.

**Theorem 10** (`Folds.unfoldSearch_foldSearch`). If no owning path is itself an entry line, every
owned line has a run of digits and a `:` or `-` separator, and no copied line looks like an entry,
then unfolding gives back the input exactly.

*Proof.* By induction on the lines, carrying the current owner. The fold prints a header only right
before an entry. A copied line is followed by a header, another copied line or the end, and none of
these parse as entries. So the one-line lookahead tells a header from a copied line, and each entry
is rebuilt as `path{sep}{num}{sep}{text}`. ∎

**Theorem 11** (`Folds.unfold_foldSearchChecked`). Whenever `fold_search` folds, unfolding gives back
the input exactly; only the owner classification remains a hypothesis. *Proof:* the refusal
supplies Theorem 10's condition on copied lines. ∎

**Theorem 12** (`Folds.foldSearch_not_injective`). The refusal is necessary: without it, two different
inputs fold to the same output when a copied line looks like an entry. These two inputs did:

```text
longpath.py:1:a          longpath.py:1:a
longpath.py:2:b          longpath.py:2:b
  3: c                   longpath.py:3:c
```

`fold_search` now refuses the first and folds the second. The model's digits are ASCII; Python's
`\d` also matches other Unicode decimal digits, and the code's refusal uses `\d` too, so it refuses
at least what the model does.

`test_fold_paths_round_trip` generates 2,000 path lists. It adds an entry that starts with spaces to
some of them and checks that `fold_paths` refuses all 273 of those, since an indented head would
break Theorem 9; of the rest, 937 fold and unfold to their exact input. `test_fold_search_round_trip`
generates 3,000 search outputs, some with match lines whose path looks like an entry. It checks that
`fold_search` refuses all 1,996 that contain a line that looks like an entry, and that 287 of the
rest fold and unfold to their exact input. Letting `_PATH` accept a leading space, removing the
whitespace rules from `_SUSPECT_PATH`, or removing the refusal makes the matching test fail.

## 4. Tool routing drops only auxiliary tools, and a resume keeps its session's list

Source: `select_excluded_tools`, `CAPABILITY_GROUPS`, `recorded_tools` and `lean_command` in
`brainspace_copilot_bridge.py`. Lean: `TokenMasterProofs/Routing.lean`.

`LEAN_EXCLUDED_TOOLS` is every family's tools in source order: 13 tools in 7 families. The excluded
list is that list filtered by a `keep` set, built from the families whose trigger fired (a prompt
pattern; `--agent`, `--fleet`, `--resume`, `-r` or `--continue`; a slash command or a verb that names
an installed skill or agent, or a built-in agent command such as `/review`) and the tools in
`TOKENMASTER_KEEP_TOOLS`. A kept `skill` also keeps the two workflow tools and the four
subagent tools, since a skill may start a workflow or hand work to a subagent.

The excluded list is computed at launch and passed as a flag, so it stays the same for the life of
the process. A resumed session runs the launcher again, and Copilot CLI sends the session's history
with the new launch's tools. So a launch that resumes a session sends the list recorded for it
instead: `resumed r s` is the recorded list `r`, less what the resume's `TOKENMASTER_KEEP_TOOLS` alone
keeps (which also drops anything outside `LEAN_EXCLUDED_TOOLS`), or, with no record, the routed list
for the resume's own signals `s`.

**Theorem 13.** For every set of signals:

- `Routing.excluded_subset_lean`: every excluded tool is in `LEAN_EXCLUDED_TOOLS`.
- `Routing.core_never_excluded`: `view`, `edit`, `create`, `rg`, `glob`, `powershell` and
  `report_intent` are never excluded.
- `Routing.kept_not_excluded`, `Routing.fired_family_kept`, `Routing.env_tool_kept`: a kept tool, a
  tool of a family that fired, and a tool named in `TOKENMASTER_KEEP_TOOLS` are not excluded.
- `Routing.workflows_follow_skill`: keeping `skill` keeps `run_dynamic_workflow` and
  `dynamic_workflows_manage`.
- `Routing.agents_follow_skill`: keeping `skill` keeps `task`, `read_agent`, `write_agent` and
  `list_agents`.
- `Routing.nothing_fires_excludes_all`: with no signal, all 13 tools are excluded.

For a routed launch that resumes a session, whatever list was recorded for it:

- `Routing.resume_same_list`: if the first launch's list is recorded, a resume sends it again,
  whatever prompt and routing flags the resume has, as long as its `TOKENMASTER_KEEP_TOOLS` names
  nothing the first launch's did not.
- `Routing.resume_chain_keeps_first_list`: so does every later resume that the launcher ties to the
  session, each given the list the launch before it recorded.
- `Routing.resumed_env_kept`: a tool named in the resume's `TOKENMASTER_KEEP_TOOLS` is not excluded.
- `Routing.resumed_subset_lean`, `Routing.resumed_core_never_excluded`: a resume excludes only
  tools in `LEAN_EXCLUDED_TOOLS`, so never a core tool.
- `Routing.resume_without_record`: with no record, a resume is routed like any launch.

`--all-tools` and the user's own tool flags skip routing, so the model does not cover them: a resume
with `--all-tools` sends every tool, and later resumes keep that list.

*Proof.* Membership in a filtered list. The core tools are not in the lean list, which Lean checks by
evaluation; each other fact follows from the tool being in `keep`. What `TOKENMASTER_KEEP_TOOLS`
alone keeps, a launch whose own `TOKENMASTER_KEEP_TOOLS` names at least those tools keeps too, so its
routed list passes the resume's filter unchanged, and the chain follows by induction on the
resumes. ∎

What this does not cover is whether a prompt's need fires a trigger: that is the regular
expressions' job, and they miss some phrasings. "have an agent review this diff" fires no family,
so `task` is excluded (finding 2). `test_routing_lists_match_the_lean_model` checks that the code's
families are exactly the model's, tool by tool, and three more tests check each trigger, `--agent`,
`--fleet`, `--resume`, `-r`, `TOKENMASTER_KEEP_TOOLS`, the skill rule and the no-signal case on the real
function.

Nor does it cover which record applies; the model takes the record as given. `recorded_tools` takes
the latest launch that resumed the session, else the launch that started it: the only new launch in
the session's folder that saw the session start in its first two minutes, and saw no other session
start there. `test_routing_resume_keeps_the_first_list` starts a session with each trigger's prompt
through `main`, resumes it with every trigger's prompt, and checks the list each time; it also checks
that a tool `TOKENMASTER_KEEP_TOOLS` names is kept on a resume, that a recorded core tool is not
excluded, and that a session no launch recorded is routed as before. A resume that the launcher
cannot tie to a record still gets a newly routed list: a session started without the launcher, with
the user's own tool flags or with `--worktree`, one that two launches may have started, one named by
its name or a task ID, and a bare `--resume`, which opens a picker.

## 5. Sessions in one folder can share a cached system prompt

Source: `stable_session_prefix` in `brainspace/native_transport.py`. Lean:
`TokenMasterProofs/SessionPrefix.lean`.

Copilot CLI writes each session's folder, which contains the session id, into its system prompt as
`Session folder: <path>`. When exactly one such line comes before the first user message, the bridge
replaces it with `Session folder: stated in the first user message` and prepends
`Session folder: <path>` and a blank line to the first user message. Otherwise the request passes
through unchanged.

**Theorem 14** (`SessionPrefix.system_same_across_sessions`). Two sessions whose system prompts differ
only in the path get the same rewritten system prompt. *Proof:* the rewritten prompt does not contain
the path. ∎

Sessions share the cached system prompt only when the rest of their system prompts is identical and
each has exactly one folder line; the theorem says the path itself no longer stands in the way.

**Theorem 15** (`SessionPrefix.folder_recoverable`). If neither path contains a newline, equal
rewritten first user messages have equal paths and equal original messages:

```math
\ell \mathbin{+\!\!+} p_1 \mathbin{+\!\!+} \texttt{"\textbackslash n\textbackslash n"} \mathbin{+\!\!+} t_1
= \ell \mathbin{+\!\!+} p_2 \mathbin{+\!\!+} \texttt{"\textbackslash n\textbackslash n"} \mathbin{+\!\!+} t_2
\implies p_1 = p_2 \wedge t_1 = t_2,
```

where $\ell$ is `Session folder: `. *Proof.* Neither $\ell$ nor a path contains a newline, so the first
newline of each side comes right after the path. Two lists that agree up to their first newline, and
neither of which has a newline before it, agree on what comes before it and on the rest. ∎

Python strips whitespace around the path before moving it, so that whitespace is not recovered
(finding 3). `test_session_prefix_same_system_and_recoverable_folder` checks both theorems on the
real function.

## 6. Navigation results stay within 2,400 tokens

Source: `_fit`, `_assemble`, `BUDGET` and the tools in `brainspace/symbol_index.py`. Lean:
`TokenMasterProofs/NavCap.lean`.

A tool result is one of three things: a short fixed message (an error or "no match", any echoed
argument cut to 100 characters); the uncut text of a range, returned only after the whole text,
header and any note included, is measured within `BUDGET`; or the output of `_assemble`.
`_assemble` takes `_fit`'s per-line estimate as a first guess for how many entries to show, then
measures the whole joined text with its header and footer, and shows one entry fewer until it fits.
If the header and footer alone do not fit, it cuts the text until it does.

**Theorem 16** (`NavCap.fit_prefix`, `NavCap.fit_cost_le`). `_fit` returns a prefix of its input,
and the cost of what it keeps, each entry plus one for its newline, is at most its budget.
*Proof:* by induction on the entries. ∎

**Theorem 17** (`NavCap.shrink_le`, `NavCap.shrink_maximal`). `_assemble` never shows more entries
than the first guess, and shows the most entries, up to that guess, whose whole text fits.
*Proof:* by induction on the guess. ∎

**Theorem 18** (`NavCap.assemble_le`). For any token counter under which the empty text fits, every
result `_assemble` returns costs at most the budget.

*Proof.* Whatever the number of entries, the last step cuts the text to four fifths of its length
until it fits. Each cut shortens a non-empty text, so within as many steps as the text has
characters it either fits or is empty, and the empty text fits. ∎

The bound is in the counter the navigation server uses: the exact cl100k count when the vocabulary is
installed, otherwise the fallback estimate. The fallback can undercount cl100k several times over for
non-ASCII text, so without the vocabulary a result could still pass the 3,000 tokens at which v6
would digest it.

**Theorem 19** (`NavCap.uncut_overflow_attained`). Counting the pieces is not counting the whole:
under the fallback estimate $\lceil \lvert s\rvert / 4 \rceil$, a 16-character header and a
9,584-character body cost 2,400 counted apart and 2,401 joined by a newline. ∎

Theorem 19 is why the code measures the whole text. Before this change, `_lines` compared the header
and the body counted apart, and every tool added its footer lines outside the budget `_fit` got:
`read` on a 200-line file of 9,584 characters returned 2,401 tokens under the fallback estimate, and
`locate("util.py")` on a repository with 700 files named `util.py` returned 2,401 under cl100k. Now
that `locate` returns 2,396 tokens, and that `read` no longer fits uncut: it returns its first 183
lines in 2,219 tokens. Across the 16 body sizes around it, the largest `read` result is 2,400 tokens,
for bodies of 9,580 to 9,583 characters, which still fit uncut.

`test_navigation_results_within_budget` checks `locate`, an outline, `_not_one_file`, `read`, a range
and `impact` against `BUDGET`. `test_uncut_read_within_budget` checks `read` across 16 body sizes
around the old overflow under the fallback estimate. `test_assemble_matches_the_lean_model` runs
`_assemble` on 400 random inputs and checks that it returns exactly the model's text, within the
budget, including when the header and footer alone do not fit.

## 7. The measurement method

Source: `evidence/default-routing-20261027/PROTOCOL.md` and `analyze.py`, the method PRS-6 used.
Lean: `TokenMasterProofs/Measurement.lean`.

The Lean file does not model `analyze.py`. It defines the protocol's quantities and proves the
properties the protocol relies on; the tests then check `analyze.py`'s recorded outputs against
those definitions.

All numbers come from Copilot CLI's `assistant_usage_events`: GitHub's token counts, its charge in
nano-AIU and its per-token prices. Raw tokens are input plus output over all calls of a session.
As-run cost is the sum of the charges. Cold-repriced cost adds, for the session's first main-agent
call with $r$ cache-read tokens and prices $p_{\mathrm{read}}, p_{\mathrm{write}}$:

```math
\mathit{cold} = \mathit{asRun} + r\,(p_{\mathrm{write}} - p_{\mathrm{read}}).
```

**Theorem 20** (`Measurement.cold_term_is_coldened_charge`). The added term is exactly how much more
that call would be charged on a cold cache, with every cache read turned into a cache write.
*Proof:* expand both charges; everything cancels except $r\,p_{\mathrm{write}} - r\,p_{\mathrm{read}}$. ∎

**Theorem 21** (`Measurement.asRun_le_cold`). If $p_{\mathrm{read}} \le p_{\mathrm{write}}$ and
$r \ge 0$, then $\mathit{asRun} \le \mathit{cold}$. ∎

The savings estimate is a paired ratio of sums over tasks, $\sum \mathit{tm} / \sum \mathit{stock} - 1$.
For the 95% CI, `analyze.py` sorts 10,000 bootstrap statistics, each the same ratio over tasks drawn
with replacement, and takes the 251st and the 9,751st (indices 250 and 9,750).

**Theorem 22** (`Measurement.ratio_of_sums_ge`, `Measurement.ratio_of_sums_le`). If every task's
ratio $\mathit{tm}_t/\mathit{stock}_t$ is at least (at most) $n/d$, so is the ratio of sums. In whole
numbers:

```math
\bigl(\forall t,\ n \cdot \mathit{stock}_t \le d \cdot \mathit{tm}_t\bigr) \implies n \sum_t \mathit{stock}_t \le d \sum_t \mathit{tm}_t .
```

*Proof:* add the inequalities. ∎

**Theorem 23** (`Measurement.resample_within_task_range`). A resample is any list drawn from the
tasks, so its statistic, and with it each end of the interval, lies between the smallest and the
largest single-task ratio. ∎

**Theorem 24** (`Measurement.hero_monotone`). The protocol's check, "up to $x$% fewer" holds when the
upper end of the CI of the reduction is at least $x$, is monotone: if it accepts $x$ it accepts every
smaller $x$. ∎

Checks on the recorded data:

- `test_cache_writes_never_cost_less_than_reads`: of the 521 recorded sessions, 36 list both a
  cache-read and a cache-write price, all from the default-routing study, and their 109 calls share
  one pair: 100,000 nano-AIU per cache-read token and 1,250,000 per cache-write token.
- `test_cold_repricing_matches_the_definition`: for all 30 sessions of the default-routing study, the
  recorded cold cost is the as-run cost plus the term above, within one nano-AIU.
- `test_bootstrap_interval_within_task_range`: the raw-token CI, −52.84% to −41.74%, lies within the
  per-task range of −64.45% to −26.01%; the cold-cost CI, −48.20% to −42.66%, lies within −54.87% to
  −37.63%. Both point estimates equal the ratio of sums.
- `test_hero_verdicts_follow_the_rule`: both hero verdicts in `analysis.json` follow the rule.

Not covered: whether the bootstrap interval has 95% coverage, which is a statistical property of the
resampling scheme and an assumption of the protocol, and the Wilcoxon and Holm-Bonferroni steps.

## Findings

Writing and reviewing the proofs found these gaps between the code's claims and its behavior, and
they are not fixed. Findings 1 and 2 have a `test_finding_*` test that reproduces them.

1. A lone surrogate in a tool output makes the pinned counter raise inside `rewrite_request`, so the
   bridge fails that call and every later call that resends the output.
2. The routing triggers miss some phrasings: "have an agent review this diff" excludes `task`
   (section 4).
3. Whitespace around the session folder path is not recovered after the move (section 5).

## Fixed

These gaps were found the same way and are fixed; the sections above describe the code as it is now.

- A resumed session ran the routing again, and `--resume` and `--continue` kept `session_store_sql`,
  so the tool list, part of the cached prefix, changed at a resume. A resume that the launcher ties
  to the session's record now sends the recorded list; other resumes are routed again (section 4).
- Navigation results could exceed `BUDGET`: footers sat outside the budget, and the uncut `read`
  branch did not count one newline (2,401 tokens observed). Every result is now measured whole
  (section 6).
- `fold_search` was not lossless when a copied line looked like a folded entry; it now refuses to
  fold such input (section 3).
- `fold_paths` dropped trailing newlines; it now keeps them (section 3).
- `plan_v6_request`, and twice the runtime, reverted every message of a v6 request when the request
  measured no smaller on the JSON wire, which is not what a provider bills, so that call missed the
  cached prefix. v6 shaping without guidance is no longer reverted on the whole request's token count,
  except where shaping would pass a `max_input_tokens` cap (section 2).

## Files

| File | Covers |
| --- | --- |
| `TokenMasterProofs/Cache.lean` | sections 1 and 2 |
| `TokenMasterProofs/Shaping.lean`, `TokenMasterProofs/Policy.lean` | section 2 |
| `TokenMasterProofs/Folds.lean` | section 3 |
| `TokenMasterProofs/Routing.lean` | section 4 |
| `TokenMasterProofs/SessionPrefix.lean` | section 5 |
| `TokenMasterProofs/NavCap.lean` | section 6 |
| `TokenMasterProofs/Measurement.lean` | section 7 |
