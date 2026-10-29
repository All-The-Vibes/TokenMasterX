/-!
# Navigation result size

Source: `_fit`, `_assemble`, `BUDGET` and the tools `locate`, `read_symbol` (`read`) and `impact` in
`token-master-plugin/skills/token-master/brainspace/symbol_index.py`.

A tool result is a short fixed message (an error or "no match", any echoed argument cut to 100
characters), the uncut text of a range, returned only after the whole text is measured within
`BUDGET`, or the output of `_assemble`. `_assemble` takes `_fit`'s per-line estimate as a first guess
for how many entries to show, measures the whole joined text with its footer, and shows one entry
fewer until it fits; if even the header and footer alone do not fit, it cuts the text. Because the
whole text is measured, the bound holds for any token counter.

Counting the pieces is not enough, which is why the code measures the whole text:
`uncut_overflow_attained` gives a header and a body whose separate costs fit at 2,400 and whose join
costs 2,401 under the fallback estimate. The code before this change made exactly that comparison.
-/
namespace TokenMasterProofs.NavCap

/-- `_fit`: keep leading lines while each costs its tokens plus one newline within the remaining budget. -/
def fit {α : Type} (cost : α → Nat) : Nat → List α → List α
  | _, [] => []
  | b, x :: xs => if cost x + 1 ≤ b then x :: fit cost (b - (cost x + 1)) xs else []

/-- `_fit` returns a prefix of its input. -/
theorem fit_prefix {α : Type} (cost : α → Nat) (b : Nat) (xs : List α) : fit cost b xs <+: xs := by
  induction xs generalizing b with
  | nil => exact List.nil_prefix
  | cons x xs ih =>
    unfold fit
    split
    · exact List.prefix_cons_inj x |>.mpr (ih _)
    · exact List.nil_prefix

/-- What `_fit` keeps costs at most its budget, newlines included. -/
theorem fit_cost_le {α : Type} (cost : α → Nat) (b : Nat) (xs : List α) :
    ((fit cost b xs).map (fun x => cost x + 1)).sum ≤ b := by
  induction xs generalizing b with
  | nil => simp [fit]
  | cons x xs ih =>
    unfold fit
    split
    · have := ih (b - (cost x + 1))
      simp only [List.map_cons, List.sum_cons]
      omega
    · simp

/-- The fallback estimate, `ceil(characters / 4)`. -/
def est (s : List Char) : Nat := (s.length + 3) / 4

/-- Counting the pieces is not counting the whole: under the fallback estimate, a 16-character header
and a 9,584-character body cost 2,400 counted apart and 2,401 joined by a newline. -/
theorem uncut_overflow_attained :
    est (List.replicate 16 'h') + est (List.replicate 9584 'b') = 2400 ∧
      est (List.replicate 16 'h' ++ '\n' :: List.replicate 9584 'b') = 2401 := by
  simp only [est, List.length_append, List.length_cons, List.length_replicate]
  decide

/-- `_assemble`'s loop: from the first guess `k`, show `k` entries if the whole text fits, else one
fewer, down to none. -/
def shrink (fits : Nat → Bool) : Nat → Nat
  | 0 => 0
  | k + 1 => if fits (k + 1) then k + 1 else shrink fits k

/-- `_assemble`'s last step: cut the text to four fifths of its length until it fits. The loop runs at
most once per character, so `n` steps with `n` above the length are enough. -/
def cutN (cnt : List Char → Nat) (budget : Nat) : Nat → List Char → List Char
  | 0, t => t
  | n + 1, t => if cnt t ≤ budget then t else cutN cnt budget n (t.take (t.length * 4 / 5))

/-- `_assemble`: the whole text with `shrink` entries shown, then cut until it fits. -/
def assemble (cnt : List Char → Nat) (budget : Nat) (render : Nat → List Char) (guess : Nat) : List Char :=
  let t := render (shrink (fun k => decide (cnt (render k) ≤ budget)) guess)
  cutN cnt budget (t.length + 1) t

/-- `_assemble` never shows more entries than the first guess. -/
theorem shrink_le (fits : Nat → Bool) : ∀ k, shrink fits k ≤ k
  | 0 => Nat.le_refl 0
  | k + 1 => by
    unfold shrink
    split
    · exact Nat.le_refl _
    · exact Nat.le_succ_of_le (shrink_le fits k)

/-- It shows the most entries, up to the guess, whose whole text fits: every larger count up to the
guess does not fit. -/
theorem shrink_maximal (fits : Nat → Bool) :
    ∀ k j, shrink fits k < j → j ≤ k → fits j = false
  | 0, j, h, hj => by simp [shrink] at h; omega
  | k + 1, j, h, hj => by
    unfold shrink at h
    split at h
    · omega
    · rename_i hk
      by_cases hjk : j = k + 1
      · subst hjk
        simpa using hk
      · exact shrink_maximal fits k j h (by omega)

private theorem cutN_le (cnt : List Char → Nat) (budget : Nat) (hempty : cnt [] ≤ budget) :
    ∀ (n : Nat) (t : List Char), t.length < n → cnt (cutN cnt budget n t) ≤ budget
  | 0, _, h => absurd h (Nat.not_lt_zero _)
  | n + 1, t, h => by
    unfold cutN
    split
    · assumption
    · rename_i hc
      have hne : t ≠ [] := fun ht => hc (ht ▸ hempty)
      have hpos : 0 < t.length := List.length_pos_iff.mpr hne
      apply cutN_le cnt budget hempty n
      simp only [List.length_take]
      omega

/-- Every result `_assemble` returns costs at most the budget. The only hypothesis is that the empty
text fits, which holds for both the exact count and the fallback estimate. -/
theorem assemble_le (cnt : List Char → Nat) (budget : Nat) (hempty : cnt [] ≤ budget)
    (render : Nat → List Char) (guess : Nat) : cnt (assemble cnt budget render guess) ≤ budget :=
  cutN_le cnt budget hempty _ _ (Nat.lt_succ_self _)

end TokenMasterProofs.NavCap
