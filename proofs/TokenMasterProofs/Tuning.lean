/-!
# What a keyword router costs to tune

Source: the regular expressions of `CAPABILITY_GROUPS` and the opt-in Microsoft-Decision-1 (MD-1) router,
`MD1_QUESTIONS` and `md1_families`, in `token-master-plugin/skills/token-master/brainspace_copilot_bridge.py`.

A family's pattern is an alternation of branches, and it fires on a prompt when one branch matches.
`occurs b p` says branch `b` matches prompt `p`; it is a parameter, so a branch may be any regular
expression. A pattern must keep its family for the phrasings that need it (`covers`) and, so that
`--lean` still saves tokens, fire on none of the prompts that do not (`clean`).

Call phrasings independent when any branch that matches two of them also matches a prompt that
does not need the family. Then a clean pattern that covers `n` independent phrasings has at least
`n` branches (`branches_ge_phrasings`): each phrasing needs a branch of its own. So the pattern
grows with every new way of asking that shares no safe keyword with the old ones. "have an agent
review this diff" and "farm out the lint fixes to a couple of agents" share "agent", but so does
"rename the AgentConfig class", which does not need the subagent tools.

MD-1 asks one fixed question a family whatever the phrasings, so `MD1_QUESTIONS` stays at 7
entries; its recall is measured (`evals/md1_routing_eval.py`), not proven.
-/
namespace TokenMasterProofs.Tuning

variable {P B : Type} (occurs : B → P → Bool)

/-- A pattern's alternation fires when one of its branches matches. -/
def fires (branches : List B) (p : P) : Bool := branches.any (fun b => occurs b p)

/-- Every phrasing in `pos` keeps the family. -/
def covers (branches : List B) (pos : List P) : Prop := ∀ p ∈ pos, fires occurs branches p = true

/-- No prompt in `neg` keeps the family. -/
def clean (branches : List B) (neg : List P) : Prop := ∀ n ∈ neg, fires occurs branches n = false

/-- A branch that matches two different phrasings also matches a prompt that must not fire. -/
def independent (pos neg : List P) : Prop :=
  ∀ (b : B) (p q : P), p ∈ pos → q ∈ pos → p ≠ q → occurs b p = true → occurs b q = true → ∃ n ∈ neg, occurs b n = true

/-- In a clean pattern, no branch matches two different independent phrasings. -/
theorem branch_matches_one (branches : List B) (pos neg : List P)
    (hc : clean occurs branches neg) (hi : independent occurs pos neg) {b : B} (hb : b ∈ branches)
    {p q : P} (hp : p ∈ pos) (hq : q ∈ pos) (hbp : occurs b p = true) (hbq : occurs b q = true) : p = q := by
  apply Classical.byContradiction
  intro hne
  obtain ⟨n, hn, hbn⟩ := hi b p q hp hq hne hbp hbq
  have hfires : fires occurs branches n = true := List.any_eq_true.mpr ⟨b, hb, hbn⟩
  rw [hc n hn] at hfires
  exact Bool.false_ne_true hfires

/-- A list splits into the elements a test keeps and the ones it drops. -/
theorem length_filter_split {α : Type} (f : α → Bool) :
    ∀ l : List α, (l.filter f).length + (l.filter (fun a => !f a)).length = l.length
  | [] => rfl
  | a :: l => by
      have ih := length_filter_split f l
      cases h : f a <;> simp [h] <;> omega

/-- Phrasings that no branch matches two of fit in no fewer branches than phrasings: by induction on the
branches, removing the phrasings the first branch matches (at most one). -/
theorem length_le_of_unique : ∀ (branches : List B) (pos : List P), pos.Nodup →
    (∀ p ∈ pos, ∃ b ∈ branches, occurs b p = true) →
    (∀ b ∈ branches, ∀ p ∈ pos, ∀ q ∈ pos, occurs b p = true → occurs b q = true → p = q) →
    pos.length ≤ branches.length
  | [], [], _, _, _ => Nat.le_refl 0
  | [], p :: _, _, hcov, _ => by
      obtain ⟨b, hb, _⟩ := hcov p (List.mem_cons_self ..)
      cases hb
  | b :: rest, pos, hnd, hcov, huniq => by
      let left := pos.filter (fun p => !occurs b p)
      have hleft : left.length ≤ rest.length := by
        apply length_le_of_unique rest left (hnd.filter _)
        · intro p hp
          have ⟨hpos, hnb⟩ := List.mem_filter.mp hp
          obtain ⟨c, hc, hcp⟩ := hcov p hpos
          cases List.mem_cons.mp hc with
          | inl h => subst h; simp [hcp] at hnb
          | inr h => exact ⟨c, h, hcp⟩
        · intro c hc p hp q hq
          exact huniq c (List.mem_cons_of_mem _ hc) p (List.mem_filter.mp hp).1 q (List.mem_filter.mp hq).1
      have hmatched : (pos.filter (fun p => occurs b p)).length ≤ 1 := by
        match hm : pos.filter (fun p => occurs b p) with
        | [] => simp
        | [_] => simp
        | p :: q :: _ =>
          have hp := List.mem_filter.mp (hm ▸ List.mem_cons_self .. : p ∈ pos.filter (fun p => occurs b p))
          have hq := List.mem_filter.mp
            (hm ▸ List.mem_cons_of_mem _ (List.mem_cons_self ..) : q ∈ pos.filter (fun p => occurs b p))
          have hpq : p = q := huniq b (List.mem_cons_self ..) p hp.1 q hq.1 hp.2 hq.2
          have hnd' := hm ▸ hnd.filter (fun p => occurs b p)
          simp [hpq] at hnd'
      have hsplit := length_filter_split (fun p => occurs b p) pos
      have hl : left.length = (pos.filter (fun p => !occurs b p)).length := rfl
      simp only [List.length_cons]
      omega

/-- A clean pattern that keeps the family for `n` different independent phrasings has at least `n`
branches. -/
theorem branches_ge_phrasings (branches : List B) (pos neg : List P) (hnd : pos.Nodup)
    (hcov : covers occurs branches pos) (hc : clean occurs branches neg) (hi : independent occurs pos neg) :
    pos.length ≤ branches.length :=
  length_le_of_unique occurs branches pos hnd
    (fun p hp => List.any_eq_true.mp (hcov p hp))
    (fun _b hb _p hp _q hq hbp hbq => branch_matches_one occurs branches pos neg hc hi hb hp hq hbp hbq)

/-- So every new independent phrasing costs the pattern a branch: a clean pattern that covered `pos` and
also covers one more independent phrasing is longer than `pos`. -/
theorem new_phrasing_needs_a_branch (branches : List B) (pos neg : List P) (p : P) (hnd : (p :: pos).Nodup)
    (hcov : covers occurs branches (p :: pos)) (hc : clean occurs branches neg)
    (hi : independent occurs (p :: pos) neg) : pos.length < branches.length :=
  branches_ge_phrasings occurs branches (p :: pos) neg hnd hcov hc hi

end TokenMasterProofs.Tuning
