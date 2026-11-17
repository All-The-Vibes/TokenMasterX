/-!
# The fixed-bet token test

Source: `bet_passes`, `bet_minimum_samples` and `token_upper` in
`token-master-plugin/skills/token-master/brainspace/certification.py`.

For a round of `n` paired tasks with cap `B` (`token_cap`), minimum saving `η = e / d`
(`minimum_token_reduction`, the exact value of the stored number) and level `p / q = alpha_round / 2`
(the stored float, exactly), the token side passes when

    alpha_round / 2 * Π_i (B + Ta_i - Tb_i) ≥ (B + η) ^ n,

the capital after betting the largest fraction the cap allows, `1 / (B + η)`, on each task's saving
`S_i = Ta_i - Tb_i` beyond `η`. Multiplied through by `q * d ^ n` it is `passes p q c xs` below, with
`c = d * B + e` and `xs_i = d * (B + Ta_i - Tb_i)`.

Proved: every factor is nonnegative under the cap; how the stored token bound makes the shared pass
rule decide as the bet did; the decision is monotone in every task's tokens and in each task's saving
alone, and does not depend on task order; a computable minimum `n` (7 for the default configuration);
the incumbent floor; for independent tasks with finitely many outcomes each, which may differ, that
the expected capital is at most 1 and the chance of passing at most `p / q` whenever the average
expected saving is at most `η` (Markov's inequality and the AM-GM inequality, both proved here), with
an example where the bound is attained; and that the check of the cap after each run is sound for the
totals counted at most the cap.

Not modelled: floats; that the Python computes these integers (conformance tests); independence
across tasks (assumed, as for today's gate); irrational probabilities; drawing tasks without
replacement from a pool (cited); the union bound over rounds (cited, as today).
-/
namespace TokenMasterProofs.Bet

/-! ## Lists of whole numbers -/

def prod : List Nat → Nat
  | [] => 1
  | x :: xs => x * prod xs

def sum : List Nat → Nat
  | [] => 0
  | x :: xs => x + sum xs

/-! ## The rule -/

/-- The token condition passes when `q * c ^ n ≤ p * Π xs`. -/
def passes (p q c : Nat) (xs : List Nat) : Prop := q * c ^ xs.length ≤ p * prod xs

instance (p q c : Nat) (xs : List Nat) : Decidable (passes p q c xs) :=
  inferInstanceAs (Decidable (_ ≤ _))

/-- One task's scaled factor, `d * (B + Ta - Tb)`. -/
def factor (B d : Nat) (t : Nat × Nat) : Nat := d * (B + t.1 - t.2)

/-- Under the cap (`Tb ≤ B`) the factor's natural-number subtraction is exact: it is
`B + (Ta - Tb)`, which is nonnegative. -/
theorem factor_exact {B Ta Tb : Nat} (h : Tb ≤ B) :
    ((B + Ta - Tb : Nat) : Int) = (B : Int) + ((Ta : Int) - Tb) ∧ 0 ≤ (B : Int) + ((Ta : Int) - Tb) := by
  omega

/-- Any bet of at most the largest size keeps the capital nonnegative: with bet `u / v ≤ 1` of
`1 / (B + η)`, the factor `1 + (u / v) (S - η) / (B + η)`, scaled by `v * (d * B + e)`, is
`v * (d * B + e) + u * (d * S - e)`, and it is nonnegative when `S = Ta - Tb ≥ -B`. -/
theorem bet_factor_nonneg {B Ta Tb d e u v : Int} (hTa : 0 ≤ Ta) (hTb : Tb ≤ B) (hB : 0 ≤ B)
    (hd : 0 ≤ d) (he : 0 ≤ e) (hu : 0 ≤ u) (huv : u ≤ v) :
    0 ≤ v * (d * B + e) + u * (d * (Ta - Tb) - e) := by
  have h1 : 0 ≤ (v - u) * (d * B + e) :=
    Int.mul_nonneg (by omega) (Int.add_nonneg (Int.mul_nonneg hd hB) he)
  have h2 : 0 ≤ u * (d * (B + Ta - Tb)) := Int.mul_nonneg hu (Int.mul_nonneg hd (by omega))
  have h3 : v * (d * B + e) + u * (d * (Ta - Tb) - e)
      = (v - u) * (d * B + e) + u * (d * (B + Ta - Tb)) := by grind
  omega

/-! ## How the bet enters the shared pass rule -/

/-- The shared pass rule (`certification.passes` in the margin plan, `Gate.lean`), over scaled
integers: quality bound at least `-margin`, token bound at most `-required`. -/
def passRule (margin lower upper required : Int) : Bool :=
  decide (-margin ≤ lower) && decide (upper ≤ -required)

/-- What `token_upper` stores for a bet spec: `-required` when the bet passes, and the trivial
bound `S` (the scaled `1.0`) when it fails. -/
def betUpper (S required : Int) (betOK : Bool) : Int := if betOK then -required else S

/-- Storing those values makes the shared rule accept exactly when the quality bound holds and
the bet passes, so `_saved_certificate` and `_deployment_certificate` decide as `certify` did. -/
theorem bet_upper_decides {S required margin lower : Int} (hr : 0 < required) (hS : 0 ≤ S)
    (betOK : Bool) :
    passRule margin lower (betUpper S required betOK) required
      = (decide (-margin ≤ lower) && betOK) := by
  cases betOK <;> simp [passRule, betUpper] <;> omega

/-! ## More saving never turns a pass into a fail -/

/-- Same length, and each task of the second list saves at least as much: at least as many
incumbent tokens and at most as many candidate tokens. -/
def MoreSaving : List (Nat × Nat) → List (Nat × Nat) → Prop
  | [], [] => True
  | t :: ts, t' :: ts' => (t.1 ≤ t'.1 ∧ t'.2 ≤ t.2) ∧ MoreSaving ts ts'
  | _, _ => False

theorem factor_mono {B d : Nat} {t t' : Nat × Nat} (h : t.1 ≤ t'.1 ∧ t'.2 ≤ t.2) :
    factor B d t ≤ factor B d t' :=
  Nat.mul_le_mul_left d (by omega)

theorem MoreSaving.length_eq : ∀ {ts ts' : List (Nat × Nat)}, MoreSaving ts ts' →
    ts.length = ts'.length
  | [], [], _ => rfl
  | _ :: _, _ :: _, h => by simp [MoreSaving.length_eq h.2]
  | [], _ :: _, h => h.elim
  | _ :: _, [], h => h.elim

theorem prod_factor_mono {B d : Nat} : ∀ {ts ts' : List (Nat × Nat)}, MoreSaving ts ts' →
    prod (ts.map (factor B d)) ≤ prod (ts'.map (factor B d))
  | [], [], _ => Nat.le_refl _
  | _ :: _, _ :: _, h => Nat.mul_le_mul (factor_mono h.1) (prod_factor_mono h.2)
  | [], _ :: _, h => h.elim
  | _ :: _, [], h => h.elim

/-- Monotone: if each task saves at least as much, a pass stays a pass. -/
theorem passes_mono {p q c B d : Nat} {ts ts' : List (Nat × Nat)} (h : MoreSaving ts ts')
    (hp : passes p q c (ts.map (factor B d))) : passes p q c (ts'.map (factor B d)) := by
  unfold passes at *
  rw [List.length_map] at *
  rw [← MoreSaving.length_eq h]
  exact Nat.le_trans hp (Nat.mul_le_mul_left p (prod_factor_mono h))

/-! ## A computable minimum number of tasks -/

theorem prod_le_pow {m : Nat} : ∀ {xs : List Nat}, (∀ x ∈ xs, x ≤ m) → prod xs ≤ m ^ xs.length
  | [], _ => Nat.le_refl _
  | x :: xs, h => by
    simp only [prod, List.length_cons, Nat.pow_succ]
    rw [Nat.mul_comm (m ^ xs.length) m]
    exact Nat.mul_le_mul (h x (List.mem_cons_self ..))
      (prod_le_pow (fun y hy => h y (List.mem_cons_of_mem _ hy)))

/-- A saving never exceeds `B` (the incumbent used at most `B`, the candidate at least 0), so
every factor is at most `d * (B + B)`. -/
theorem factor_le {B d : Nat} {t : Nat × Nat} (h : t.1 ≤ B) : factor B d t ≤ d * (B + B) :=
  Nat.mul_le_mul_left d (by omega)

/-- With every factor at most `m`, a pass needs `q * c ^ n ≤ p * m ^ n`. -/
theorem passes_needs {p q c m : Nat} {xs : List Nat} (hp : passes p q c xs)
    (hm : ∀ x ∈ xs, x ≤ m) : q * c ^ xs.length ≤ p * m ^ xs.length :=
  Nat.le_trans hp (Nat.mul_le_mul_left p (prod_le_pow hm))

/-- The first `n ≥ i`, searching `fuel` more values, with `q * c ^ n ≤ p * m ^ n`. -/
def firstPass (p q c m : Nat) : Nat → Nat → Nat
  | i, 0 => i
  | i, fuel + 1 => if q * c ^ i ≤ p * m ^ i then i else firstPass p q c m (i + 1) fuel

theorem firstPass_le {p q c m n : Nat} (hn : q * c ^ n ≤ p * m ^ n) :
    ∀ fuel i, i ≤ n → n ≤ i + fuel → firstPass p q c m i fuel ≤ n
  | 0, i, hi, _ => by simp only [firstPass]; exact hi
  | fuel + 1, i, hi, hf => by
    simp only [firstPass]
    split
    · exact hi
    · rename_i hne
      have hin : i ≠ n := fun h => hne (h ▸ hn)
      exact firstPass_le hn fuel (i + 1) (by omega) (by omega)

/-- The smallest round size at which the best possible outcome passes, searched up to `bound`. -/
def minSamples (p q c m bound : Nat) : Nat := firstPass p q c m 0 bound

/-- No round smaller than `minSamples` can pass. -/
theorem minSamples_le {p q c m bound : Nat} {xs : List Nat} (hp : passes p q c xs)
    (hm : ∀ x ∈ xs, x ≤ m) (hb : xs.length ≤ bound) : minSamples p q c m bound ≤ xs.length :=
  firstPass_le (passes_needs hp hm) bound 0 (Nat.zero_le _) (by omega)

/-- The default configuration: `B = 100000`, `η = 1` (so `d = e = 1`), round 1 at `α = 0.05`,
whose stored `alpha_round` is exactly `4380576431005153 / 2 ^ 57`, so `p / q` is that over 2. -/
def pDefault : Nat := 4380576431005153
def qDefault : Nat := 2 * 144115188075855872

theorem default_min_samples : minSamples pDefault qDefault 100001 200000 64 = 7 := by decide

theorem default_seven_can_pass : passes pDefault qDefault 100001 (List.replicate 7 200000) := by
  unfold passes; decide

theorem default_six_cannot :
    ¬ passes pDefault qDefault 100001 (List.replicate 6 200000) := by
  unfold passes; decide

/-! ## Finitely many outcomes per task: the capital's expectation and the chance of passing -/

/-- One task's outcomes as (whole-number weight, scaled factor) pairs. -/
abbrev Dist := List (Nat × Nat)

/-- Total weight of a task's outcomes (the common denominator of its probabilities). -/
def mass : Dist → Nat
  | [] => 0
  | o :: D => o.1 + mass D

/-- Weighted sum of a task's factors: `mass D` times its expected factor. -/
def moment : Dist → Nat
  | [] => 0
  | o :: D => o.1 * o.2 + moment D

/-- Prepend each outcome of one task to every outcome sequence of the later tasks. -/
def expand : Dist → List (List (Nat × Nat)) → List (List (Nat × Nat))
  | [], _ => []
  | o :: D, ss => ss.map (o :: ·) ++ expand D ss

/-- Every way the tasks can come out, one outcome per task. -/
def outcomes : List Dist → List (List (Nat × Nat))
  | [] => [[]]
  | D :: Ds => expand D (outcomes Ds)

def weight (s : List (Nat × Nat)) : Nat := prod (s.map Prod.fst)
def capital (s : List (Nat × Nat)) : Nat := prod (s.map Prod.snd)

def total (f : List (Nat × Nat) → Nat) : List (List (Nat × Nat)) → Nat
  | [] => 0
  | s :: ss => f s + total f ss

theorem total_append (f : List (Nat × Nat) → Nat) :
    ∀ a b : List (List (Nat × Nat)), total f (a ++ b) = total f a + total f b
  | [], b => by simp [total]
  | s :: a, b => by simp only [List.cons_append, total, total_append f a b]; omega

theorem wc_cons (o : Nat × Nat) (s : List (Nat × Nat)) :
    weight (o :: s) * capital (o :: s) = o.1 * o.2 * (weight s * capital s) := by
  simp only [weight, capital, List.map_cons, prod]; grind

theorem w_cons (o : Nat × Nat) (s : List (Nat × Nat)) : weight (o :: s) = o.1 * weight s := by
  simp only [weight, List.map_cons, prod]

theorem total_map_cons_moment (o : Nat × Nat) :
    ∀ ss : List (List (Nat × Nat)),
      total (fun s => weight s * capital s) (ss.map (o :: ·))
        = o.1 * o.2 * total (fun s => weight s * capital s) ss
  | [] => by simp [total]
  | s :: ss => by
    simp only [List.map_cons, total]
    rw [total_map_cons_moment o ss, wc_cons, Nat.mul_add]

theorem total_map_cons_weight (o : Nat × Nat) :
    ∀ ss : List (List (Nat × Nat)), total weight (ss.map (o :: ·)) = o.1 * total weight ss
  | [] => by simp [total]
  | s :: ss => by
    simp only [List.map_cons, total]
    rw [total_map_cons_weight o ss, w_cons, Nat.mul_add]

theorem expand_moment (ss : List (List (Nat × Nat))) : ∀ D : Dist,
    total (fun s => weight s * capital s) (expand D ss)
      = moment D * total (fun s => weight s * capital s) ss
  | [] => by simp [expand, total, moment]
  | o :: D => by
    simp only [expand, total_append, total_map_cons_moment, expand_moment ss D, moment]
    grind

theorem expand_weight (ss : List (List (Nat × Nat))) : ∀ D : Dist,
    total weight (expand D ss) = mass D * total weight ss
  | [] => by simp [expand, total, mass]
  | o :: D => by
    simp only [expand, total_append, total_map_cons_weight, expand_weight ss D, mass]
    grind

/-- Independence across tasks: summing weight times capital over every outcome sequence gives
the product of the tasks' weighted factor sums. -/
theorem outcomes_moment : ∀ Ds : List Dist,
    total (fun s => weight s * capital s) (outcomes Ds) = prod (Ds.map moment)
  | [] => by simp [outcomes, total, weight, capital, prod]
  | D :: Ds => by simp only [outcomes, expand_moment, outcomes_moment Ds, List.map_cons, prod]

theorem outcomes_weight : ∀ Ds : List Dist, total weight (outcomes Ds) = prod (Ds.map mass)
  | [] => by simp [outcomes, total, weight, prod]
  | D :: Ds => by simp only [outcomes, expand_weight, outcomes_weight Ds, List.map_cons, prod]

theorem mem_expand_length {D : Dist} {ss : List (List (Nat × Nat))} {n : Nat}
    (hss : ∀ s ∈ ss, s.length = n) : ∀ s ∈ expand D ss, s.length = n + 1 := by
  induction D with
  | nil => intro s hs; simp [expand] at hs
  | cons o D ih =>
    intro s hs
    simp only [expand, List.mem_append, List.mem_map] at hs
    rcases hs with ⟨s', hs', rfl⟩ | hs
    · simp [hss s' hs']
    · exact ih s hs

theorem outcomes_length : ∀ (Ds : List Dist), ∀ s ∈ outcomes Ds, s.length = Ds.length
  | [] => by intro s hs; simp [outcomes] at hs; simp [hs]
  | D :: Ds => by
    intro s hs
    simpa using mem_expand_length (outcomes_length Ds) s hs

/-- Weight of the outcome sequences that pass. -/
def passWeight (p q c : Nat) (s : List (Nat × Nat)) : Nat :=
  if passes p q c (s.map Prod.snd) then weight s else 0

theorem total_markov (p q c n : Nat) : ∀ ss : List (List (Nat × Nat)),
    (∀ s ∈ ss, s.length = n) →
    q * c ^ n * total (passWeight p q c) ss ≤ p * total (fun s => weight s * capital s) ss
  | [], _ => by simp [total]
  | s :: ss, h => by
    have ih := total_markov p q c n ss (fun t ht => h t (List.mem_cons_of_mem _ ht))
    have hs : s.length = n := h s (List.mem_cons_self ..)
    have one : q * c ^ n * passWeight p q c s ≤ p * (weight s * capital s) := by
      unfold passWeight
      split
      · rename_i hp
        unfold passes at hp
        rw [List.length_map, hs] at hp
        unfold capital
        calc q * c ^ n * weight s = weight s * (q * c ^ n) := Nat.mul_comm _ _
          _ ≤ weight s * (p * prod (s.map Prod.snd)) := Nat.mul_le_mul_left _ hp
          _ = p * (weight s * prod (s.map Prod.snd)) := by grind
      · simp
    simp only [total, Nat.mul_add]
    exact Nat.add_le_add one ih

/-! ## The AM-GM inequality, by Bernoulli's inequality -/

theorem square_nonneg (y : Int) : 0 ≤ y * y := by
  rcases Int.le_total 0 y with h | h
  · exact Int.mul_nonneg h h
  · have h2 := Int.mul_nonneg (by omega : 0 ≤ -y) (by omega : 0 ≤ -y)
    have e : -y * -y = y * y := by grind
    rw [e] at h2
    exact h2

/-- Bernoulli's inequality, homogeneous form: `a ^ m * (a + (m + 1) y) ≤ (a + y) ^ (m + 1)`. -/
theorem bernoulli {a y : Int} (ha : 0 ≤ a) (hay : 0 ≤ a + y) : ∀ m : Nat,
    a ^ m * (a + ((m : Int) + 1) * y) ≤ (a + y) ^ (m + 1)
  | 0 => by simp [Int.pow_one]
  | m + 1 => by
    have ih := bernoulli ha hay m
    have hP : 0 ≤ a ^ m := Int.pow_nonneg ha
    have h1 : a ^ m * (a + ((m : Int) + 1) * y) * (a + y) ≤ (a + y) ^ (m + 1) * (a + y) :=
      Int.mul_le_mul_of_nonneg_right ih hay
    have h2 : 0 ≤ ((m : Int) + 1) * a ^ m * (y * y) :=
      Int.mul_nonneg (Int.mul_nonneg (by omega) hP) (square_nonneg y)
    have e1 : a ^ m * (a + ((m : Int) + 1) * y) * (a + y)
        = a ^ (m + 1) * (a + (((m + 1 : Nat) : Int) + 1) * y) + ((m : Int) + 1) * a ^ m * (y * y) := by
      rw [Int.pow_succ]; push_cast; grind
    have e2 : (a + y) ^ (m + 1 + 1) = (a + y) ^ (m + 1) * (a + y) := Int.pow_succ _ _
    rw [e2]
    omega

/-- One new value against the mean of `n` others:
`(n + 1) ^ (n + 1) * x * S ^ n ≤ n ^ n * (x + S) ^ (n + 1)`. -/
theorem amgm_step (n x S : Nat) :
    (n + 1) ^ (n + 1) * x * S ^ n ≤ n ^ n * (x + S) ^ (n + 1) := by
  rcases Nat.eq_zero_or_pos n with rfl | hn
  · simp
  · have ha : (0 : Int) ≤ ((n : Int) + 1) * (S : Int) := Int.mul_nonneg (by omega) (by omega)
    have hsum : ((n : Int) + 1) * (S : Int) + ((n : Int) * x - S) = (n : Int) * ((x : Int) + S) := by
      grind
    have hay : (0 : Int) ≤ ((n : Int) + 1) * (S : Int) + ((n : Int) * x - S) := by
      rw [hsum]; exact Int.mul_nonneg (by omega) (by omega)
    have hb := bernoulli ha hay n
    have hlin : ((n : Int) + 1) * (S : Int) + ((n : Int) + 1) * ((n : Int) * x - S)
        = ((n : Int) + 1) * ((n : Int) * x) := by grind
    rw [hsum, hlin, Int.mul_pow, Int.mul_pow] at hb
    have key : (n : Int) * (((n : Int) + 1) ^ (n + 1) * x * (S : Int) ^ n)
        ≤ (n : Int) * ((n : Int) ^ n * ((x : Int) + S) ^ (n + 1)) := by
      have l : (n : Int) * (((n : Int) + 1) ^ (n + 1) * x * (S : Int) ^ n)
          = ((n : Int) + 1) ^ n * (S : Int) ^ n * (((n : Int) + 1) * ((n : Int) * x)) := by
        rw [Int.pow_succ ((n : Int) + 1) n]; grind
      have r : (n : Int) * ((n : Int) ^ n * ((x : Int) + S) ^ (n + 1))
          = (n : Int) ^ (n + 1) * ((x : Int) + S) ^ (n + 1) := by
        rw [Int.pow_succ (n : Int) n]; grind
      rw [l, r]; exact hb
    have key2 := Int.le_of_mul_le_mul_left key (by omega : (0 : Int) < n)
    exact_mod_cast key2

/-- AM-GM over whole numbers: `n ^ n * Π l ≤ (Σ l) ^ n` for a list `l` of length `n`. -/
theorem amgm : ∀ l : List Nat, l.length ^ l.length * prod l ≤ sum l ^ l.length
  | [] => by simp [prod, sum]
  | x :: t => by
    have ih := amgm t
    have hstep := amgm_step t.length x (sum t)
    have hpos : 0 < t.length ^ t.length := by
      rcases Nat.eq_zero_or_pos t.length with h | h
      · rw [h]; decide
      · exact Nat.pow_pos h
    simp only [List.length_cons, prod, sum]
    refine Nat.le_of_mul_le_mul_left ?_ hpos
    calc t.length ^ t.length * ((t.length + 1) ^ (t.length + 1) * (x * prod t))
        = (t.length + 1) ^ (t.length + 1) * x * (t.length ^ t.length * prod t) := by grind
      _ ≤ (t.length + 1) ^ (t.length + 1) * x * (sum t ^ t.length) := Nat.mul_le_mul_left _ ih
      _ ≤ t.length ^ t.length * (x + sum t) ^ (t.length + 1) := hstep

/-- If `n` whole numbers sum to at most `n * K`, their product is at most `K ^ n`. -/
theorem prod_le_of_sum_le {K : Nat} (l : List Nat) (h : sum l ≤ l.length * K) :
    prod l ≤ K ^ l.length := by
  rcases Nat.eq_zero_or_pos l.length with h0 | hpos
  · rw [List.eq_nil_of_length_eq_zero h0]; exact Nat.le_refl _
  · have h2 : sum l ^ l.length ≤ (l.length * K) ^ l.length := Nat.pow_le_pow_left h _
    rw [Nat.mul_pow] at h2
    exact Nat.le_of_mul_le_mul_left (Nat.le_trans (amgm l) h2) (Nat.pow_pos hpos)

/-! ## The incumbent floor -/

/-- The factor a task would have if the candidate used no tokens: `d * (B + Ta)`. -/
def incumbentFactor (B d : Nat) (t : Nat × Nat) : Nat := d * (B + t.1)

theorem prod_factor_le_incumbent {B d : Nat} : ∀ ts : List (Nat × Nat),
    prod (ts.map (factor B d)) ≤ prod (ts.map (incumbentFactor B d))
  | [] => Nat.le_refl _
  | t :: ts => Nat.mul_le_mul (Nat.mul_le_mul_left d (by omega)) (prod_factor_le_incumbent ts)

/-- No task saves more than the incumbent used, so a pass needs
`q * c ^ n * n ^ n ≤ p * (Σ_i d * (B + Ta_i)) ^ n`: the incumbent's mean tokens must reach
`(B + η) * (q / p) ^ (1 / n) - B`, the fixed-bet counterpart of `B * r + η`. -/
theorem incumbent_floor {p q c B d : Nat} (ts : List (Nat × Nat))
    (hp : passes p q c (ts.map (factor B d))) :
    q * c ^ ts.length * ts.length ^ ts.length
      ≤ p * sum (ts.map (incumbentFactor B d)) ^ ts.length := by
  unfold passes at hp
  rw [List.length_map] at hp
  have h1 := prod_factor_le_incumbent (B := B) (d := d) ts
  have h2 := amgm (ts.map (incumbentFactor B d))
  rw [List.length_map] at h2
  calc q * c ^ ts.length * ts.length ^ ts.length
      ≤ p * prod (ts.map (factor B d)) * ts.length ^ ts.length := Nat.mul_le_mul_right _ hp
    _ ≤ p * prod (ts.map (incumbentFactor B d)) * ts.length ^ ts.length :=
        Nat.mul_le_mul_right _ (Nat.mul_le_mul_left _ h1)
    _ = p * (ts.length ^ ts.length * prod (ts.map (incumbentFactor B d))) := by grind
    _ ≤ p * sum (ts.map (incumbentFactor B d)) ^ ts.length := Nat.mul_le_mul_left _ h2

/-! ## The guarantee -/

theorem prod_map_const {α : Type} (f : α → Nat) (W : Nat) :
    ∀ l : List α, (∀ D ∈ l, f D = W) → prod (l.map f) = W ^ l.length
  | [], _ => rfl
  | D :: l, h => by
    simp only [List.map_cons, prod, List.length_cons, Nat.pow_succ]
    rw [h D (List.mem_cons_self ..), prod_map_const f W l (fun E hE => h E (List.mem_cons_of_mem _ hE))]
    exact Nat.mul_comm _ _

/-- With every task's weights totalling `W`, all outcome sequences together weigh `W ^ n`, so a
sequence's chance is its weight over `W ^ n`. -/
theorem total_mass {W : Nat} (Ds : List Dist) (hW : ∀ D ∈ Ds, mass D = W) :
    total weight (outcomes Ds) = W ^ Ds.length := by
  rw [outcomes_weight, prod_map_const mass W Ds hW]

/-- Under the null, the average over tasks of the expected factor is at most `c` (the average
expected saving is at most `η`), and the expected capital is at most 1:
`Σ_s weight(s) * capital(s) ≤ (W * c) ^ n`. Tasks may differ; only their average is bounded. -/
theorem expected_capital_le_one {W c : Nat} (Ds : List Dist)
    (hnull : sum (Ds.map moment) ≤ Ds.length * (W * c)) :
    total (fun s => weight s * capital s) (outcomes Ds) ≤ (W * c) ^ Ds.length := by
  rw [outcomes_moment]
  have := prod_le_of_sum_le (Ds.map moment) (by rw [List.length_map]; exact hnull)
  rwa [List.length_map] at this

/-- Markov's inequality for the rule: under the null the passing sequences weigh at most
`p / q` of all sequences, so a false pass has chance at most `p / q = alpha_round / 2`. -/
theorem false_pass_bounded {p q c W : Nat} (hc : 0 < c) (Ds : List Dist)
    (hnull : sum (Ds.map moment) ≤ Ds.length * (W * c)) :
    q * total (passWeight p q c) (outcomes Ds) ≤ p * W ^ Ds.length := by
  have hm := total_markov p q c Ds.length (outcomes Ds) (outcomes_length Ds)
  have he := expected_capital_le_one Ds hnull
  have h3 : q * c ^ Ds.length * total (passWeight p q c) (outcomes Ds)
      ≤ c ^ Ds.length * (p * W ^ Ds.length) := by
    calc q * c ^ Ds.length * total (passWeight p q c) (outcomes Ds)
        ≤ p * total (fun s => weight s * capital s) (outcomes Ds) := hm
      _ ≤ p * (W * c) ^ Ds.length := Nat.mul_le_mul_left _ he
      _ = c ^ Ds.length * (p * W ^ Ds.length) := by rw [Nat.mul_pow]; grind
  have h4 : c ^ Ds.length * (q * total (passWeight p q c) (outcomes Ds))
      ≤ c ^ Ds.length * (p * W ^ Ds.length) := by
    calc c ^ Ds.length * (q * total (passWeight p q c) (outcomes Ds))
        = q * c ^ Ds.length * total (passWeight p q c) (outcomes Ds) := by grind
      _ ≤ _ := h3
  exact Nat.le_of_mul_le_mul_left h4 (Nat.pow_pos hc)

/-- The same as a chance: with every task's outcome weights totalling `W`, the passing
sequences' weight over the total weight `W ^ n` is at most `p / q`. -/
theorem false_pass_chance {p q c W : Nat} (hc : 0 < c) (Ds : List Dist)
    (hW : ∀ D ∈ Ds, mass D = W) (hnull : sum (Ds.map moment) ≤ Ds.length * (W * c)) :
    q * total (passWeight p q c) (outcomes Ds) ≤ p * total weight (outcomes Ds) := by
  rw [total_mass Ds hW]
  exact false_pass_bounded hc Ds hnull

/-- The bound is attained, so it is not vacuous: one task at `B = 3`, `η = 1` (`c = 4`) whose
saving is `-3` with weight 1 and `3` with weight 2 (mean saving exactly `η`); at level `2 / 3` the
passing outcome weighs 2 of 3, exactly the level. -/
def exampleTask : Dist := [(1, 0), (2, 6)]

theorem example_attained :
    sum ([exampleTask].map moment) ≤ 1 * (3 * 4) ∧
    total (passWeight 2 3 4) (outcomes [exampleTask]) = 2 ∧
    total weight (outcomes [exampleTask]) = 3 ∧
    3 * total (passWeight 2 3 4) (outcomes [exampleTask]) = 2 * 3 ^ 1 := by
  decide

/-! ## Added: task order, saving alone, and the capped abort for tasks that differ

Stated over the definitions above, with every hypothesis explicit. -/

/-! ### The task order does not matter -/

theorem prod_perm {xs ys : List Nat} (h : xs.Perm ys) : prod xs = prod ys := by
  induction h with
  | nil => rfl
  | cons x _ ih => simp [prod, ih]
  | swap x y l => simp only [prod]; exact Nat.mul_left_comm _ _ _
  | trans _ _ ih1 ih2 => exact ih1.trans ih2

/-- Reordering the tasks never changes the decision, so no order needs pre-registering. -/
theorem passes_perm {p q c : Nat} {xs ys : List Nat} (h : xs.Perm ys) :
    passes p q c xs ↔ passes p q c ys := by
  unfold passes
  rw [h.length_eq, prod_perm h]

/-! ### Monotone in each task's saving alone -/

/-- Same length, and each task of the second list saves at least as much: `Ta - Tb`, as an
integer, is not smaller. Either arm's tokens may rise or fall. -/
def SavesMore : List (Nat × Nat) → List (Nat × Nat) → Prop
  | [], [] => True
  | t :: ts, t' :: ts' => ((t.1 : Int) - t.2 ≤ (t'.1 : Int) - t'.2) ∧ SavesMore ts ts'
  | _, _ => False

theorem SavesMore.length_eq : ∀ {ts ts' : List (Nat × Nat)}, SavesMore ts ts' →
    ts.length = ts'.length
  | [], [], _ => rfl
  | _ :: _, _ :: _, h => by simp [SavesMore.length_eq h.2]
  | [], _ :: _, h => h.elim
  | _ :: _, [], h => h.elim

/-- The factor's natural-number subtraction stops at 0, which keeps it monotone in the saving, so
this needs no cap. -/
theorem factor_mono_saving {B d : Nat} {t t' : Nat × Nat}
    (h : (t.1 : Int) - t.2 ≤ (t'.1 : Int) - t'.2) : factor B d t ≤ factor B d t' :=
  Nat.mul_le_mul_left d (by omega)

theorem prod_factor_mono_saving {B d : Nat} : ∀ {ts ts' : List (Nat × Nat)}, SavesMore ts ts' →
    prod (ts.map (factor B d)) ≤ prod (ts'.map (factor B d))
  | [], [], _ => Nat.le_refl _
  | _ :: _, _ :: _, h => Nat.mul_le_mul (factor_mono_saving h.1) (prod_factor_mono_saving h.2)
  | [], _ :: _, h => h.elim
  | _ :: _, [], h => h.elim

/-- Monotone in the saving alone: if no task's saving `Ta - Tb` falls, a pass stays a pass. -/
theorem passes_mono_saving {p q c B d : Nat} {ts ts' : List (Nat × Nat)} (h : SavesMore ts ts')
    (hp : passes p q c (ts.map (factor B d))) : passes p q c (ts'.map (factor B d)) := by
  unfold passes at *
  rw [List.length_map] at *
  rw [← SavesMore.length_eq h]
  exact Nat.le_trans hp (Nat.mul_le_mul_left p (prod_factor_mono_saving h))

/-! ### The capped abort for tasks that differ

Here a task's outcomes are `(w, a)` pairs: a whole-number weight `w` and a label `a` naming one
run of both arms. Three functions read a label: `inCap a` says both arms stayed within the cap,
`obs a` is the scaled factor the code records, and `cap a` is the scaled factor the same run
would have under a live cap. The outcome's observed pair is `(w, obs a)` and its capped pair is
`(w, cap a)`. Tasks differ through their own weights and labels; give two tasks disjoint labels
and their runs are unrelated. -/

/-- A task's capped distribution: each outcome keeps its weight and takes its capped factor. -/
def capDist (cap : Nat → Nat) (D : Dist) : Dist := D.map (fun o => (o.1, cap o.2))

/-- Weight of a label sequence that certifies: every run stayed within the cap and the test
passes on the recorded factors. -/
def abortWeight (p q c : Nat) (inCap : Nat → Bool) (obs : Nat → Nat) (s : List (Nat × Nat)) :
    Nat :=
  if s.all (fun o => inCap o.2) = true ∧ passes p q c (s.map (fun o => obs o.2)) then weight s
  else 0

theorem expand_map (f : Nat × Nat → Nat × Nat) (ss : List (List (Nat × Nat))) : ∀ D : Dist,
    expand (D.map f) (ss.map (List.map f)) = (expand D ss).map (List.map f)
  | [] => rfl
  | o :: D => by
    simp only [List.map_cons, expand, List.map_append, List.map_map, expand_map f ss D]
    rfl

/-- Relabelling every outcome by `f` commutes with listing the outcome sequences. -/
theorem outcomes_map (f : Nat × Nat → Nat × Nat) : ∀ Ds : List Dist,
    outcomes (Ds.map (List.map f)) = (outcomes Ds).map (List.map f)
  | [] => rfl
  | D :: Ds => by simp only [List.map_cons, outcomes, outcomes_map f Ds, expand_map]

theorem total_map (f : List (Nat × Nat) → Nat) (g : List (Nat × Nat) → List (Nat × Nat)) :
    ∀ ss : List (List (Nat × Nat)), total f (ss.map g) = total (fun s => f (g s)) ss
  | [] => rfl
  | s :: ss => by simp only [List.map_cons, total, total_map f g ss]

theorem total_le {f g : List (Nat × Nat) → Nat} : ∀ ss : List (List (Nat × Nat)),
    (∀ s ∈ ss, f s ≤ g s) → total f ss ≤ total g ss
  | [], _ => Nat.le_refl _
  | s :: ss, h => Nat.add_le_add (h s (List.mem_cons_self ..))
      (total_le ss (fun t ht => h t (List.mem_cons_of_mem _ ht)))

/-- Capping changes factors, not weights. -/
theorem weight_cap (cap : Nat → Nat) : ∀ s : List (Nat × Nat),
    weight (s.map (fun o => (o.1, cap o.2))) = weight s
  | [] => rfl
  | o :: s => by simp only [List.map_cons, w_cons, weight_cap cap s]

/-- A certifying label sequence weighs no more than its capped sequence's pass weight: every run
in it stayed within the cap, so its recorded factors are its capped ones. -/
theorem abortWeight_le {p q c : Nat} {inCap : Nat → Bool} {obs cap : Nat → Nat}
    (hagree : ∀ a, inCap a = true → obs a = cap a) (s : List (Nat × Nat)) :
    abortWeight p q c inCap obs s ≤ passWeight p q c (s.map (fun o => (o.1, cap o.2))) := by
  unfold abortWeight
  split
  · rename_i h
    obtain ⟨hall, hp⟩ := h
    have e : s.map (fun o => obs o.2) = (s.map (fun o => (o.1, cap o.2))).map Prod.snd := by
      rw [List.map_map]
      exact List.map_congr_left (fun o ho => hagree o.2 (List.all_eq_true.mp hall o ho))
    rw [e] at hp
    unfold passWeight
    exact Nat.le_of_eq (by rw [ite_eq_left hp, weight_cap])
  · exact Nat.zero_le _

/-- The post-hoc abort is sound for tasks that differ. `hagree` says a run's recorded and capped
factors agree whenever it stayed within the cap. The null is `false_pass_chance`'s null on the
capped distributions. Then the label sequences in which every task stayed within the cap and the
test passes on the recorded factors weigh at most `p / q` of all sequences, however often runs
exceed the cap. The total weight is the same before and after capping (`weight_cap`), so this is
the bound `false_pass_chance` gives for the capped tasks. -/
theorem abort_sound_het {p q c W : Nat} (hc : 0 < c) (inCap : Nat → Bool) (obs cap : Nat → Nat)
    (hagree : ∀ a, inCap a = true → obs a = cap a) (Ls : List Dist)
    (hW : ∀ D ∈ Ls.map (capDist cap), mass D = W)
    (hnull : sum ((Ls.map (capDist cap)).map moment) ≤ (Ls.map (capDist cap)).length * (W * c)) :
    q * total (abortWeight p q c inCap obs) (outcomes Ls) ≤ p * total weight (outcomes Ls) := by
  have h := false_pass_chance (p := p) (q := q) hc (Ls.map (capDist cap)) hW hnull
  rw [show Ls.map (capDist cap) = Ls.map (List.map (fun o => (o.1, cap o.2))) from rfl,
    outcomes_map, total_map, total_map] at h
  have hw : total (fun s => weight (s.map (fun o => (o.1, cap o.2)))) (outcomes Ls)
      = total weight (outcomes Ls) := by
    simp only [weight_cap]
  rw [hw] at h
  exact Nat.le_trans (Nat.mul_le_mul_left q (total_le _ (fun s _ => abortWeight_le hagree s))) h

end TokenMasterProofs.Bet
