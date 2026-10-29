/-!
# Request planning guards

Source: `plan_request` in `token-master-plugin/skills/token-master/brainspace/request_policy.py`
(request-policy v1 to v4; v5 and v6 delegate to their own modules).

`plan_request` walks the eligible tool results in order. For each it builds a proposal, measures the
whole request with the pinned counter, and accepts the proposal only if it has strictly fewer tokens
and no more UTF-8 bytes than the request as it stands (lines 511, 561 and 624). It stops after
`max_transforms` acceptances (v4 stops after that many attempts, which also bounds acceptances).
Eligibility excludes the first `stable_prefix_messages` messages, the caller's exact-answer indices,
the newest `keep_recent_tool_results` tool results and every non-tool message. An accepted change
assigns only `message["content"]`. Policy v6 does not use this loop: `plan_v6_request` shapes every
tool result except the exact-answer indices, whatever `stable_prefix_messages` and
`keep_recent_tool_results` say.

The model takes the edits as functions on a request and the measure as a function, so it covers
every transform the code can call.
-/
namespace TokenMasterProofs.Policy

/-- A request's size: tokens under the pinned counter and UTF-8 wire bytes. -/
structure Measure where
  tokens : Nat
  bytes : Nat

/-- The acceptance test: strictly fewer tokens and no more bytes. -/
def accepts (cur prop : Measure) : Bool :=
  decide (prop.tokens < cur.tokens) && decide (prop.bytes ≤ cur.bytes)

/-- The greedy loop, stopping after `m` acceptances. Returns the final request and the number of
accepted edits; a rejected edit leaves the request unchanged. -/
def greedy {σ : Type} (meas : σ → Measure) : Nat → σ → List (σ → σ) → σ × Nat
  | _, cur, [] => (cur, 0)
  | 0, cur, _ :: _ => (cur, 0)
  | m + 1, cur, e :: es =>
    if accepts (meas cur) (meas (e cur)) then
      ((greedy meas m (e cur) es).1, (greedy meas m (e cur) es).2 + 1)
    else greedy meas (m + 1) cur es

private theorem accepts_spec {cur prop : Measure} (h : accepts cur prop = true) :
    prop.tokens < cur.tokens ∧ prop.bytes ≤ cur.bytes := by
  simpa [accepts] using h

/-- The plan never has more tokens or more bytes than the request it started from. -/
theorem greedy_never_expands {σ : Type} (meas : σ → Measure) :
    ∀ (m : Nat) (cur : σ) (es : List (σ → σ)),
      (meas (greedy meas m cur es).1).tokens ≤ (meas cur).tokens ∧
      (meas (greedy meas m cur es).1).bytes ≤ (meas cur).bytes
  | _, cur, [] => by simp [greedy]
  | 0, cur, _ :: _ => by simp [greedy]
  | m + 1, cur, e :: es => by
    unfold greedy
    split
    · rename_i h
      have ha := accepts_spec h
      have ih := greedy_never_expands meas m (e cur) es
      dsimp only
      exact ⟨by omega, by omega⟩
    · exact greedy_never_expands meas (m + 1) cur es

/-- If any edit was accepted, the plan has strictly fewer tokens than the original request. -/
theorem greedy_strict {σ : Type} (meas : σ → Measure) :
    ∀ (m : Nat) (cur : σ) (es : List (σ → σ)), 0 < (greedy meas m cur es).2 →
      (meas (greedy meas m cur es).1).tokens < (meas cur).tokens
  | _, cur, [] => by simp [greedy]
  | 0, cur, _ :: _ => by simp [greedy]
  | m + 1, cur, e :: es => by
    unfold greedy
    split
    · rename_i h
      intro _
      have ha := accepts_spec h
      have := (greedy_never_expands meas m (e cur) es).1
      dsimp only
      omega
    · exact greedy_strict meas (m + 1) cur es

/-- At most `max_transforms` edits are accepted. -/
theorem greedy_count_le {σ : Type} (meas : σ → Measure) :
    ∀ (m : Nat) (cur : σ) (es : List (σ → σ)), (greedy meas m cur es).2 ≤ m
  | _, cur, [] => by simp [greedy]
  | 0, cur, _ :: _ => by simp [greedy]
  | m + 1, cur, e :: es => by
    unfold greedy
    split
    · have := greedy_count_le meas m (e cur) es
      simp only
      omega
    · exact greedy_count_le meas (m + 1) cur es

/-- Replace the content of message `i`, keeping its metadata (role, ids, tool calls). -/
def setContent {κ τ : Type} : List (κ × τ) → Nat → τ → List (κ × τ)
  | [], _, _ => []
  | (k, _) :: ms, 0, t => (k, t) :: ms
  | m :: ms, i + 1, t => m :: setContent ms i t

/-- Apply accepted edits, each a position and its new content, in order. -/
def applyEdits {κ τ : Type} : List (κ × τ) → List (Nat × τ) → List (κ × τ)
  | ms, [] => ms
  | ms, (i, t) :: es => applyEdits (setContent ms i t) es

private theorem setContent_meta {κ τ : Type} :
    ∀ (ms : List (κ × τ)) (i : Nat) (t : τ), (setContent ms i t).map Prod.fst = ms.map Prod.fst
  | [], _, _ => rfl
  | (k, _) :: ms, 0, t => rfl
  | m :: ms, i + 1, t => by simp [setContent, setContent_meta ms i t]

private theorem setContent_other {κ τ : Type} :
    ∀ (ms : List (κ × τ)) (i j : Nat) (t : τ), j ≠ i → (setContent ms i t)[j]? = ms[j]?
  | [], _, _, _, _ => rfl
  | (k, _) :: ms, 0, j, t, h => by
    cases j with
    | zero => exact absurd rfl h
    | succ j => rfl
  | m :: ms, i + 1, j, t, h => by
    cases j with
    | zero => rfl
    | succ j => simpa [setContent] using setContent_other ms i j t (by omega)

/-- Accepted edits change no message's metadata: roles, ids, tool calls and every non-content
field stay as they were. -/
theorem metadata_unchanged {κ τ : Type} :
    ∀ (ms : List (κ × τ)) (es : List (Nat × τ)), (applyEdits ms es).map Prod.fst = ms.map Prod.fst
  | ms, [] => rfl
  | ms, (i, t) :: es => by
    simp only [applyEdits]
    rw [metadata_unchanged (setContent ms i t) es, setContent_meta]

/-- A protected position (stable prefix, exact-answer index, newest tool results, non-tool message)
is never edited, so the message there is exactly the original. -/
theorem protected_unchanged {κ τ : Type} (P : Nat → Prop) :
    ∀ (ms : List (κ × τ)) (es : List (Nat × τ)), (∀ e ∈ es, ¬ P e.1) →
      ∀ j, P j → (applyEdits ms es)[j]? = ms[j]?
  | ms, [], _, _, _ => rfl
  | ms, (i, t) :: es, hes, j, hj => by
    simp only [applyEdits]
    have hne : j ≠ i := fun h => hes (i, t) (List.mem_cons_self ..) (h ▸ hj)
    rw [protected_unchanged P (setContent ms i t) es (fun e he => hes e (List.mem_cons_of_mem _ he)) j hj,
      setContent_other ms i j t hne]

end TokenMasterProofs.Policy
