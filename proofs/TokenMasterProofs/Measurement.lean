/-!
# Measurement method

Source: `evidence/default-routing-20261027/PROTOCOL.md` and `analyze.py`, the method PRS-6 used.

Every number comes from Copilot CLI's own `assistant_usage_events`: GitHub's token counts, GitHub's
charge in nano-AIU, and GitHub's per-token prices. Raw tokens are input plus output over all calls of
a session. As-run cost is the sum of the charges. Cold-repriced cost adds, for the session's first
main-agent call, its cache-read tokens times the gap between the cache-write and cache-read prices.

The savings estimate is a paired ratio of sums, `Σ tm / Σ stock − 1`, with a 10,000-resample paired
bootstrap over tasks for the 95% CI. Ratios are compared here by cross-multiplication, so everything
stays in whole numbers. Prices are integers in this model; fractional prices scale to integers
without changing any inequality below.

What these theorems do not cover: whether the bootstrap's 95% interval has 95% coverage. That is a
statistical property of the resampling scheme, and it is an assumption of the protocol, not a theorem.
-/
namespace TokenMasterProofs.Measurement

/-- One model call. `input` counts every prompt token, cache reads and writes included. -/
structure Call where
  input : Int
  cacheRead : Int
  cacheWrite : Int
  output : Int
  pIn : Int
  pRead : Int
  pWrite : Int
  pOut : Int
  charge : Int

/-- The charge the token counts imply; `analyze.py` flags a call whose charge differs by more than 1. -/
def Call.implied (c : Call) : Int :=
  (c.input - c.cacheRead - c.cacheWrite) * c.pIn + c.cacheRead * c.pRead + c.cacheWrite * c.pWrite
    + c.output * c.pOut

/-- The same call on a cold cache: every cache read becomes a cache write. -/
def Call.coldened (c : Call) : Call :=
  { c with cacheRead := 0, cacheWrite := c.cacheWrite + c.cacheRead }

def rawTokens (cs : List Call) : Int := (cs.map fun c => c.input + c.output).sum

def asRun (cs : List Call) : Int := (cs.map Call.charge).sum

/-- PRS-6's cold re-pricing, given the session's first main-agent call. -/
def cold (first : Call) (cs : List Call) : Int :=
  asRun cs + first.cacheRead * (first.pWrite - first.pRead)

/-- The re-pricing term is exactly what that first call would have cost more on a cold cache. -/
theorem cold_term_is_coldened_charge (c : Call) :
    c.coldened.implied - c.implied = c.cacheRead * (c.pWrite - c.pRead) := by
  simp only [Call.implied, Call.coldened]
  grind

/-- Cold-repriced cost is never below as-run cost when cache writes cost at least as much as reads. -/
theorem asRun_le_cold (first : Call) (cs : List Call) (hr : 0 ≤ first.cacheRead)
    (hp : first.pRead ≤ first.pWrite) : asRun cs ≤ cold first cs := by
  have : 0 ≤ first.cacheRead * (first.pWrite - first.pRead) := Int.mul_nonneg hr (by omega)
  unfold cold
  omega

/-- One paired task: tokens (or cost) for stock Copilot CLI and for TokenMaster. -/
structure Pair where
  stock : Nat
  tm : Nat

def sumStock (ps : List Pair) : Nat := (ps.map Pair.stock).sum

def sumTm (ps : List Pair) : Nat := (ps.map Pair.tm).sum

/-- If every task's ratio `tm / stock` is at least `n / d`, the ratio of sums is too. -/
theorem ratio_of_sums_ge (n d : Nat) (ps : List Pair) (h : ∀ p ∈ ps, n * p.stock ≤ d * p.tm) :
    n * sumStock ps ≤ d * sumTm ps := by
  induction ps with
  | nil => simp [sumStock, sumTm]
  | cons p ps ih =>
    have h1 := h p (List.mem_cons_self ..)
    have h2 := ih (fun q hq => h q (List.mem_cons_of_mem _ hq))
    simp only [sumStock, sumTm, List.map_cons, List.sum_cons] at *
    rw [Nat.mul_add, Nat.mul_add]
    exact Nat.add_le_add h1 h2

/-- If every task's ratio `tm / stock` is at most `n / d`, the ratio of sums is too. -/
theorem ratio_of_sums_le (n d : Nat) (ps : List Pair) (h : ∀ p ∈ ps, d * p.tm ≤ n * p.stock) :
    d * sumTm ps ≤ n * sumStock ps := by
  induction ps with
  | nil => simp [sumStock, sumTm]
  | cons p ps ih =>
    have h1 := h p (List.mem_cons_self ..)
    have h2 := ih (fun q hq => h q (List.mem_cons_of_mem _ hq))
    simp only [sumStock, sumTm, List.map_cons, List.sum_cons] at *
    rw [Nat.mul_add, Nat.mul_add]
    exact Nat.add_le_add h1 h2

/-- A bootstrap resample draws tasks with replacement. Whatever it draws, its ratio of sums lies
between the smallest and the largest single-task ratio, so every bootstrap statistic, and with
them both ends of the percentile interval, lies in that range. -/
theorem resample_within_task_range (tasks resample : List Pair) (nlo dlo nhi dhi : Nat)
    (drawn : ∀ q ∈ resample, q ∈ tasks)
    (lo : ∀ p ∈ tasks, nlo * p.stock ≤ dlo * p.tm) (hi : ∀ p ∈ tasks, dhi * p.tm ≤ nhi * p.stock) :
    nlo * sumStock resample ≤ dlo * sumTm resample ∧ dhi * sumTm resample ≤ nhi * sumStock resample :=
  ⟨ratio_of_sums_ge nlo dlo resample (fun q hq => lo q (drawn q hq)),
   ratio_of_sums_le nhi dhi resample (fun q hq => hi q (drawn q hq))⟩

/-- The hero check: "up to x% fewer" holds when the upper end of the CI of the reduction, in
percent, is at least x. -/
def heroHolds (upperReduction x : Nat) : Prop := x ≤ upperReduction

/-- The check is monotone: if it accepts x, it accepts every smaller claim. -/
theorem hero_monotone {u x y : Nat} (h : heroHolds u x) (hy : y ≤ x) : heroHolds u y :=
  Nat.le_trans hy h

end TokenMasterProofs.Measurement
