/-!
# v6 tool-result shaping

Source: `shape_tool_result` and `plan_v6_request` in
`token-master-plugin/skills/token-master/brainspace/v6_shaping.py`.

`shape_tool_result` folds, then digests a result that is still over its budget, and finally keeps
the candidate only if it differs from the original, has fewer tokens, and has no more JSON-escaped
bytes. Everything before that last step is a function of the tool name, its arguments and the
content, so the model only needs that last step. The candidate is a parameter; `count` is the cl100k
counter on the decoded text, the text a provider bills with its own tokenizer, and `wire` the escaped
size in bytes.

`plan_v6_request` (`plan_request` with policy v6, the native runtime's default) shapes every tool
result this way and keeps the result. It used to measure the whole request on the JSON wire, where a
newline or a backslash is two characters, and revert the whole plan when that count was not smaller;
the revert changed earlier messages and missed the provider's cached prefix. It no longer reverts,
and neither does the runtime for v6 without guidance. The prefix theorem for this per-message map
is `Cache.shaping_prefix_stable`.
-/
namespace TokenMasterProofs.Shaping

/-- The final step of `shape_tool_result`. -/
def guard (count wire : String → Nat) (orig cand : String) : String :=
  if cand ≠ orig ∧ count cand < count orig ∧ wire cand ≤ wire orig then cand else orig

/-- A shaped result never has more tokens or more wire bytes than the original. -/
theorem guard_never_expands (count wire : String → Nat) (orig cand : String) :
    count (guard count wire orig cand) ≤ count orig ∧ wire (guard count wire orig cand) ≤ wire orig := by
  unfold guard
  split
  · rename_i h
    exact ⟨Nat.le_of_lt h.2.1, h.2.2⟩
  · exact ⟨Nat.le_refl _, Nat.le_refl _⟩

/-- A result that was changed has strictly fewer tokens. -/
theorem guard_strict_if_changed (count wire : String → Nat) (orig cand : String)
    (h : guard count wire orig cand ≠ orig) : count (guard count wire orig cand) < count orig := by
  unfold guard at *
  split
  · rename_i hc
    exact hc.2.1
  · rename_i hc
    simp [hc] at h

private theorem sum_map_le {α : Type} (f g : α → Nat) (h : ∀ x, f x ≤ g x) :
    ∀ xs : List α, (xs.map f).sum ≤ (xs.map g).sum
  | [] => Nat.le_refl _
  | x :: xs => by
    simp only [List.map_cons, List.sum_cons]
    exact Nat.add_le_add (h x) (sum_map_le f g h xs)

private theorem sum_map_lt {α : Type} (f g : α → Nat) (h : ∀ x, f x ≤ g x) :
    ∀ xs : List α, (∃ x ∈ xs, f x < g x) → (xs.map f).sum < (xs.map g).sum
  | [], ⟨_, hx, _⟩ => absurd hx List.not_mem_nil
  | y :: ys, ⟨x, hx, hlt⟩ => by
    simp only [List.map_cons, List.sum_cons]
    rcases List.mem_cons.mp hx with rfl | hx
    · have := sum_map_le f g h ys
      omega
    · have := sum_map_lt f g h ys ⟨x, hx, hlt⟩
      have := h y
      omega

/-- Request bytes are a fixed part plus each content's escaped size, so shaping every tool result
with the guard never adds bytes. -/
theorem request_bytes_never_grow (count wire : String → Nat) (k : Nat) (items : List (String × String)) :
    k + (items.map (fun p => wire (guard count wire p.1 p.2))).sum ≤ k + (items.map (fun p => wire p.1)).sum :=
  Nat.add_le_add_left (sum_map_le _ _ (fun p => (guard_never_expands count wire p.1 p.2).2) items) k

/-- If a prompt's token count is a fixed part plus each content's count, shaping that
changes at least one result strictly lowers it. -/
theorem billed_tokens_shrink_if_additive (count wire : String → Nat) (k : Nat) (items : List (String × String))
    (changed : ∃ p ∈ items, guard count wire p.1 p.2 ≠ p.1) :
    k + (items.map (fun p => count (guard count wire p.1 p.2))).sum < k + (items.map (fun p => count p.1)).sum := by
  have := sum_map_lt (fun p => count (guard count wire p.1 p.2)) (fun p => count p.1)
    (fun p => (guard_never_expands count wire p.1 p.2).1) items
    (let ⟨p, hp, hc⟩ := changed; ⟨p, hp, guard_strict_if_changed count wire p.1 p.2 hc⟩)
  omega

end TokenMasterProofs.Shaping
