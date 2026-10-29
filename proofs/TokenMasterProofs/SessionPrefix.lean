/-!
# Stable session prefix

Source: `stable_session_prefix` in `token-master-plugin/skills/token-master/brainspace/native_transport.py`
(Responses requests) and `rewrite_messages_request` in `brainspace_copilot_bridge.py` (Messages requests).

Copilot CLI writes each session's own folder, which contains the session id, into its system prompt
as `Session folder: <path>`. When exactly one such line comes before the first user message, the
bridge replaces it with `Session folder: stated in the first user message` and prepends
`Session folder: <path>` and a blank line to the first user message. Otherwise the request passes
through unchanged. Finding the line is a regular expression and is covered by the conformance tests;
the model starts from the found parts. Python strips the path, so the model takes a path with no
surrounding whitespace.
-/
namespace TokenMasterProofs.SessionPrefix

/-- `Session folder: ` -/
def label : List Char :=
  ['S', 'e', 's', 's', 'i', 'o', 'n', ' ', 'f', 'o', 'l', 'd', 'e', 'r', ':', ' ']

/-- The rewrite once the folder line is found: the system prompt is `pre`, the folder line, `post`.
Returns the new system prompt and the new first user message. `moved` is the constant replacement line. -/
def rewrite (moved pre path post text : List Char) : List Char × List Char :=
  (pre ++ moved ++ post, label ++ path ++ '\n' :: '\n' :: text)

/-- Two sessions in the same folder differ only in the path; after the rewrite their system prompts
are identical, so a new session's first call can reuse the cached prefix. -/
theorem system_same_across_sessions (moved pre post p₁ p₂ t₁ t₂ : List Char) :
    (rewrite moved pre p₁ post t₁).1 = (rewrite moved pre p₂ post t₂).1 := rfl

private theorem label_no_newline : '\n' ∉ label := by decide

private theorem split_at_first (c : Char) :
    ∀ (a₁ a₂ r₁ r₂ : List Char), c ∉ a₁ → c ∉ a₂ → a₁ ++ c :: r₁ = a₂ ++ c :: r₂ → a₁ = a₂ ∧ r₁ = r₂
  | [], [], _, _, _, _, h => ⟨rfl, (List.cons.inj h).2⟩
  | [], x :: _, _, _, _, h₂, h => by
    have := (List.cons.inj h).1
    subst this
    exact absurd (List.mem_cons_self ..) h₂
  | x :: _, [], _, _, h₁, _, h => by
    have := (List.cons.inj h).1
    subst this
    exact absurd (List.mem_cons_self ..) h₁
  | x :: xs, y :: ys, r₁, r₂, h₁, h₂, h => by
    have hxy := (List.cons.inj h).1
    have ih := split_at_first c xs ys r₁ r₂ (fun m => h₁ (List.mem_cons_of_mem _ m))
      (fun m => h₂ (List.mem_cons_of_mem _ m)) (List.cons.inj h).2
    exact ⟨by rw [hxy, ih.1], ih.2⟩

/-- No information is lost: a path without a newline is recovered exactly from the rewritten first
user message, and so is the original message. -/
theorem folder_recoverable (moved pre post p₁ p₂ t₁ t₂ : List Char)
    (h₁ : '\n' ∉ p₁) (h₂ : '\n' ∉ p₂)
    (h : (rewrite moved pre p₁ post t₁).2 = (rewrite moved pre p₂ post t₂).2) : p₁ = p₂ ∧ t₁ = t₂ := by
  simp only [rewrite, List.append_assoc] at h
  have hl : ∀ p, '\n' ∉ p → '\n' ∉ label ++ p := fun p hp m =>
    (List.mem_append.mp m).elim (fun x => label_no_newline x) (fun x => hp x)
  have := split_at_first '\n' (label ++ p₁) (label ++ p₂) ('\n' :: t₁) ('\n' :: t₂) (hl p₁ h₁) (hl p₂ h₂)
    (by simpa [List.append_assoc] using h)
  exact ⟨List.append_cancel_left this.1, (List.cons.inj this.2).2⟩

end TokenMasterProofs.SessionPrefix
