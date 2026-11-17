/-!
# The certification gate's pass rule, its quality margin and the exact harm test

Source: `passes`, `quality_lower` and `harm_passes` in
`token-master-plugin/skills/token-master/brainspace/certification.py`, and the true-off checks in
`brainspace/optimizer.py`.

The pass rule over scaled integers: the quality bound must be at least `-margin` and the token bound
at most `-required`. At margin 0 it is the strict rule. A margin registry stores `-margin` as its
quality bound when the exact harm count passes and the scaled `-1.0` otherwise, and uses a margin only
against the true-off policy, so margins cannot add up across promotions. `tail n l a b` is `b ^ n`
times the chance of at most `l` harms in `n` independent tasks harmed with probability `a / b`;
`harmPasses` is the integer test the code runs.

Not modelled: floats, the statistical coverage events (Hoeffding on the token side, the binomial tail
on the quality side, both cited) and that the Python computes these integers (conformance tests).
-/
namespace TokenMasterProofs.Gate

/-- Pass rule (G) with a margin: quality bound at least `-margin`, token bound at most `-required`. -/
def passes (margin lower upper required : Int) : Bool :=
  decide (-margin ≤ lower) && decide (upper ≤ -required)

/-- At margin 0 the rule is today's strict rule. -/
theorem zero_margin_is_strict (lower upper required : Int) :
    passes 0 lower upper required = (decide (0 ≤ lower) && decide (upper ≤ -required)) := by
  simp [passes]

/-- A larger margin never turns a pass into a fail. -/
theorem margin_monotone {m m' lower upper required : Int} (h : m ≤ m')
    (hp : passes m lower upper required = true) : passes m' lower upper required = true := by
  simp [passes] at *
  omega

/-- On the coverage event (true quality difference at least the bound, true token difference at
most the bound), a pass implies non-inferiority within the margin and the required saving. -/
theorem sound_on_coverage {m lower upper required μq μt : Int}
    (hq : lower ≤ μq) (ht : μt ≤ upper) (hp : passes m lower upper required = true) :
    -m ≤ μq ∧ μt ≤ -required := by
  simp [passes] at hp
  omega

/-- E[D] = P(only the candidate passes) - P(only the incumbent passes) is at least minus the harm
rate, so a harm rate within the margin is non-inferior within the margin. -/
theorem harm_within_margin {win harm m : Int} (hw : 0 ≤ win) (hh : harm ≤ m) :
    -m ≤ win - harm := by
  omega

/-- At a positive margin `quality_lower` stores `-margin` when the exact harm test passes and `-S`
(the scaled `-1.0`) otherwise; with `margin < S` the pass rule then accepts exactly when the harm
test passes and the token bound holds. -/
def marginLower (S margin : Int) (harmOK : Bool) : Int := if harmOK then -margin else -S

theorem margin_lower_decides {S margin upper required : Int} (hm : margin < S) (harmOK : Bool) :
    passes margin (marginLower S margin harmOK) upper required = (harmOK && decide (upper ≤ -required)) := by
  cases harmOK <;> simp [passes, marginLower] <;> omega

/-- One promotion: incumbent, candidate and the round's margin. Policies are numbered. -/
structure Step where
  incumbent : Nat
  candidate : Nat
  margin : Int

/-- The champion after a chain of promotions from `start`. -/
def last (start : Nat) : List Step → Nat
  | [] => start
  | s :: rest => last s.candidate rest

/-- Each promotion's incumbent is the champion before it. -/
def Chain (start : Nat) : List Step → Prop
  | [] => True
  | s :: rest => s.incumbent = start ∧ Chain s.candidate rest

/-- No compounding: if a positive margin is only ever used against the one reference policy, every
champion stays above any `b` that bounds both the starting policy and `q ref - δ`. -/
theorem no_compounding (q : Nat → Int) (ref : Nat) (δ b : Int) :
    ∀ (start : Nat) (steps : List Step), b ≤ q start → b ≤ q ref - δ → Chain start steps →
    (∀ s ∈ steps, (s.margin = 0 ∨ s.incumbent = ref) ∧ s.margin ≤ δ) →
    (∀ s ∈ steps, q s.incumbent - s.margin ≤ q s.candidate) →
    b ≤ q (last start steps) := by
  intro start steps
  induction steps generalizing start with
  | nil => intro h _ _ _ _; simpa [last] using h
  | cons s rest ih =>
    intro hstart hb hc hr hcert
    obtain ⟨hinc, hrest⟩ := hc
    have hs := hr s (List.mem_cons_self ..)
    have hcs := hcert s (List.mem_cons_self ..)
    have hnext : b ≤ q s.candidate := by
      rcases hs with ⟨h0 | href, hm⟩
      · rw [h0, hinc] at hcs; omega
      · rw [href] at hcs; omega
    exact ih s.candidate hnext hb hrest (fun t ht => hr t (List.mem_cons_of_mem _ ht))
      (fun t ht => hcert t (List.mem_cons_of_mem _ ht))

/-- Starting at the reference, every champion is within `δ` of it. -/
theorem within_margin_of_reference (q : Nat → Int) (ref : Nat) (δ : Int) (hδ : 0 ≤ δ)
    (steps : List Step) (hc : Chain ref steps)
    (hr : ∀ s ∈ steps, (s.margin = 0 ∨ s.incumbent = ref) ∧ s.margin ≤ δ)
    (hcert : ∀ s ∈ steps, q s.incumbent - s.margin ≤ q s.candidate) :
    q ref - δ ≤ q (last ref steps) :=
  no_compounding q ref δ (q ref - δ) ref steps (by omega) (Int.le_refl _) hc hr hcert

/-- Without the rule, three certified steps with margin 1 each lose 3, not 1. -/
def exampleSteps : List Step := [⟨0, 1, 1⟩, ⟨1, 2, 1⟩, ⟨2, 3, 1⟩]

def exampleQ (i : Nat) : Int := -(i : Int)

theorem compounding_example :
    Chain 0 exampleSteps ∧ (∀ s ∈ exampleSteps, exampleQ s.incumbent - s.margin ≤ exampleQ s.candidate) ∧
      exampleQ (last 0 exampleSteps) = exampleQ 0 - 3 ∧ ¬ (exampleQ 0 - 1 ≤ exampleQ (last 0 exampleSteps)) := by
  refine ⟨?_, ?_, ?_, ?_⟩
  · simp [Chain, exampleSteps]
  · decide
  · decide
  · decide


/-- `b ^ n * P(Bin(n, a / b) ≤ l)`, by recursion on the last task. -/
def tail : Nat → Nat → Nat → Nat → Nat
  | 0, _, _, _ => 1
  | n+1, 0, a, b => (b - a) * tail n 0 a b
  | n+1, l+1, a, b => (b - a) * tail n (l+1) a b + a * tail n l a b

/-- Allowing more harms never lowers the tail. -/
theorem tail_mono_l (h : l ≤ l') : tail n l a b ≤ tail n l' a b := by
  induction n generalizing l l' with
  | zero => exact Nat.le_refl _
  | succ n ih =>
    cases l with
    | zero =>
      cases l' with
      | zero => exact Nat.le_refl _
      | succ k =>
        simp only [tail]
        exact Nat.le_add_right_of_le (Nat.mul_le_mul_left _ (ih (Nat.zero_le _)))
    | succ j =>
      cases l' with
      | zero => omega
      | succ k =>
        simp only [tail]
        exact Nat.add_le_add (Nat.mul_le_mul_left _ (ih h))
          (Nat.mul_le_mul_left _ (ih (Nat.le_of_succ_le_succ h)))

/-- A higher harm rate never makes few harms more likely. -/
theorem tail_antitone (h1 : a ≤ a') (h2 : a' ≤ b) : tail n l a' b ≤ tail n l a b := by
  induction n generalizing l with
  | zero => exact Nat.le_refl _
  | succ n ih =>
    cases l with
    | zero =>
      simp only [tail]
      exact Nat.mul_le_mul (by omega) ih
    | succ k =>
      simp only [tail]
      have i1 : (b - a') * tail n (k+1) a' b ≤ (b - a') * tail n (k+1) a b :=
        Nat.mul_le_mul_left _ ih
      have i2 : a' * tail n k a' b ≤ a' * tail n k a b := Nat.mul_le_mul_left _ ih
      have i3 : (a' - a) * tail n k a b ≤ (a' - a) * tail n (k+1) a b :=
        Nat.mul_le_mul_left _ (tail_mono_l (Nat.le_succ k))
      have e1 : (b - a) * tail n (k+1) a b
          = (b - a') * tail n (k+1) a b + (a' - a) * tail n (k+1) a b := by
        rw [← Nat.add_mul]; congr 1; omega
      have e2 : a' * tail n k a b = a * tail n k a b + (a' - a) * tail n k a b := by
        rw [← Nat.add_mul]; congr 1; omega
      omega

/-- The exact harm test: the chance of at most `l` harms is at most `p / q`. -/
def harmPasses (n l a b p q : Nat) : Prop := q * tail n l a b ≤ p * b ^ n

/-- The pass region is downward closed in the harm count. -/
theorem passes_down (h : harmPasses n l a b p q) (hl : l' ≤ l) : harmPasses n l' a b p q :=
  Nat.le_trans (Nat.mul_le_mul_left q (tail_mono_l hl)) h

/-- If the true harm rate `ah / b` is at least the margin `a / b`, the chance of a passing harm
count is at most `p / q`. -/
theorem false_pass_bounded (h1 : a ≤ ah) (h2 : ah ≤ b) (hp : harmPasses n l a b p q) :
    q * tail n l ah b ≤ p * b ^ n :=
  Nat.le_trans (Nat.mul_le_mul_left q (tail_antitone h1 h2)) hp

/-- With no harms allowed the test reads `q * (b - a) ^ n ≤ p * b ^ n`. -/
theorem zero_harm_iff : harmPasses n 0 a b p q ↔ q * (b - a) ^ n ≤ p * b ^ n := by
  have h : ∀ m, tail m 0 a b = (b - a) ^ m := by
    intro m
    induction m with
    | zero => rfl
    | succ m ih => rw [Nat.pow_succ', ← ih]; rfl
  unfold harmPasses
  rw [h]

/-- At margin 0 the count test never passes when `p / q < 1`. -/
theorem count_test_needs_margin (hb : 0 < b) (hpq : p < q) : ¬ harmPasses n l 0 b p q := by
  intro h
  have h0 := zero_harm_iff.mp (passes_down h (Nat.zero_le l))
  rw [Nat.sub_zero] at h0
  have := Nat.le_of_mul_le_mul_right h0 (Nat.pow_pos hb)
  omega

end TokenMasterProofs.Gate
