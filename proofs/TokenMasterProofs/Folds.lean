/-!
# Lossless folds

Source: `fold_paths` and `fold_search` in
`token-master-plugin/skills/token-master/brainspace/v6_shaping.py`.

Both functions split the text into lines and join their output with newlines. The model works on
lines, each a list of characters, and takes the classification the Python makes (which lines are
entries, which path owns a search line) as given. The hypotheses say what that classification must
guarantee; the conformance tests check that the Python's regular expressions guarantee it.

`fold_paths` prints a directory head whenever the directory changes (`.` for an empty head), then
each name indented by two spaces, then the `[...]` notices and the input's trailing newlines. It
refuses an empty line inside the list, so an empty line in its output can only be a trailing one.

`fold_search` prints one header per file and each owned line as `  {line}{sep} {text}`; a line no
file owns is copied as it is, and if such a line looks like a folded entry, it refuses to fold
(`foldSearchChecked`). `foldSearch_not_injective` shows why the refusal is needed. Digits are ASCII
here; Python's `\d` also accepts other Unicode decimal digits, and its refusal covers those too.
-/
namespace TokenMasterProofs.Folds

abbrev Line := List Char

/-- Starts with two spaces. -/
def indented : Line → Bool
  | ' ' :: ' ' :: _ => true
  | _ => false

/-! ## `fold_paths` -/

/-- The printed head: `.` for an empty head. -/
def headLine (h : Line) : Line := if h = [] then ['.'] else h

/-- `fold_paths` once its checks pass. Each entry is `(head, name)` with `head ++ name` the
original path; `cur` is the head printed last. -/
def foldPaths (cur : Option Line) : List (Line × Line) → List Line
  | [] => []
  | (h, n) :: es => (if cur = some h then [] else [headLine h]) ++ (' ' :: ' ' :: n) :: foldPaths (some h) es

/-- The inverse: an indented line is a name under the current head, an empty line or a notice
passes through, and any other line sets the head. -/
def unfoldPaths (isNotice : Line → Bool) (cur : Line) : List Line → List Line
  | [] => []
  | l :: ls =>
    if indented l then (cur ++ l.drop 2) :: unfoldPaths isNotice cur ls
    else if l.isEmpty || isNotice l then l :: unfoldPaths isNotice cur ls
    else unfoldPaths isNotice (if l = ['.'] then [] else l) ls

/-- What the Python's checks guarantee for an entry: its printed head is not indented and not a
notice, and a head is never the line `.` itself. -/
def GoodEntry (isNotice : Line → Bool) (e : Line × Line) : Prop :=
  indented (headLine e.1) = false ∧ isNotice (headLine e.1) = false ∧ e.1 ≠ ['.']

/-- A line of the tail: a notice or a trailing empty line, never indented. -/
def Tail (isNotice : Line → Bool) (x : Line) : Prop := indented x = false ∧ (x.isEmpty || isNotice x) = true

private theorem headLine_nonempty (h : Line) : (headLine h).isEmpty = false := by
  unfold headLine
  split
  · rfl
  · rename_i hh
    cases h with
    | nil => exact absurd rfl hh
    | cons _ _ => rfl

private theorem notices_pass (isNotice : Line → Bool) :
    ∀ (ns : List Line) (cur : Line), (∀ x ∈ ns, Tail isNotice x) →
      unfoldPaths isNotice cur ns = ns
  | [], _, _ => rfl
  | x :: xs, cur, h => by
    have hx := h x (List.mem_cons_self ..)
    simp [unfoldPaths, hx.1, hx.2, notices_pass isNotice xs cur (fun y hy => h y (List.mem_cons_of_mem _ hy))]

private theorem head_back (h : Line) (hg : h ≠ ['.']) :
    (if headLine h = ['.'] then [] else headLine h) = h := by
  unfold headLine
  by_cases he : h = []
  · simp [he]
  · simp [he, hg]

private theorem unfold_foldPaths_from (isNotice : Line → Bool) (ns : List Line)
    (hn : ∀ x ∈ ns, Tail isNotice x) :
    ∀ (es : List (Line × Line)) (cur : Option Line) (cl : Line), (∀ h, cur = some h → cl = h) →
      (∀ e ∈ es, GoodEntry isNotice e) →
      unfoldPaths isNotice cl (foldPaths cur es ++ ns) = es.map (fun e => e.1 ++ e.2) ++ ns
  | [], _, cl, _, _ => by simpa [foldPaths] using notices_pass isNotice ns cl hn
  | (h, n) :: es, cur, cl, hcl, hes => by
    have hg := hes (h, n) (List.mem_cons_self ..)
    have ih := unfold_foldPaths_from isNotice ns hn es (some h) h (fun _ hh => Option.some.inj hh)
      (fun e he => hes e (List.mem_cons_of_mem _ he))
    by_cases hc : cur = some h
    · have : cl = h := hcl h hc
      subst this
      simp [foldPaths, hc, unfoldPaths, indented, ih]
    · simp only [foldPaths, hc, ite_false, List.cons_append, List.nil_append, List.map_cons]
      rw [unfoldPaths]
      simp only [hg.1, hg.2.1, headLine_nonempty, Bool.false_or, Bool.false_eq_true, ite_false,
        head_back h hg.2.2]
      simp [unfoldPaths, indented, ih]

/-- `fold_paths` is lossless: unfolding its output gives back every path, every notice and every
trailing empty line, in order, so at the text level it gives back the input exactly. -/
theorem unfoldPaths_foldPaths (isNotice : Line → Bool) (es : List (Line × Line)) (ns : List Line)
    (hes : ∀ e ∈ es, GoodEntry isNotice e) (hn : ∀ x ∈ ns, Tail isNotice x) :
    unfoldPaths isNotice [] (foldPaths none es ++ ns) = es.map (fun e => e.1 ++ e.2) ++ ns :=
  unfold_foldPaths_from isNotice ns hn es none [] (fun _ h => by cases h) hes

/-! ## `fold_search` -/

/-- A search line as `fold_search` classifies it: owned by a path, or copied as it is. -/
inductive SLine where
  | owned (path : Line) (sep : Char) (num : Line) (rest : Line)
  | plain (l : Line)

/-- The original text of the line: `path{sep}{num}{sep}{rest}`. -/
def SLine.orig : SLine → Line
  | .owned p c n r => p ++ c :: (n ++ c :: r)
  | .plain l => l

/-- The folded entry `  {num}{sep} {rest}`. -/
def entryLine (c : Char) (n r : Line) : Line := ' ' :: ' ' :: (n ++ c :: ' ' :: r)

/-- `fold_search`: a header when the owner changes, then the entry; a plain line resets the owner. -/
def foldSearch (cur : Option Line) : List SLine → List Line
  | [] => []
  | .owned p c n r :: xs => (if cur = some p then [] else [p]) ++ entryLine c n r :: foldSearch (some p) xs
  | .plain l :: xs => l :: foldSearch none xs

/-- Parse `  {digits}{sep} {rest}`, taking the longest run of digits as `\d+` does. -/
def parseEntry : Line → Option (Char × Line × Line)
  | ' ' :: ' ' :: t =>
    match t.dropWhile Char.isDigit with
    | c :: ' ' :: r =>
      if t.takeWhile Char.isDigit ≠ [] ∧ (c = ':' ∨ c = '-') then some (c, t.takeWhile Char.isDigit, r)
      else none
    | _ => none
  | _ => none

/-- Whether the next line is a folded entry. -/
def nextIsEntry : List Line → Bool
  | m :: _ => (parseEntry m).isSome
  | [] => false

/-- The inverse: an entry line is rebuilt under the current header; a non-entry line is a header
when an entry follows it, and is copied otherwise. -/
def unfoldSearch : Option Line → List Line → List Line
  | _, [] => []
  | cur, l :: ls =>
    match parseEntry l with
    | some (c, n, r) =>
      (match cur with
       | some p => p ++ c :: (n ++ c :: r)
       | none => l) :: unfoldSearch cur ls
    | none => if nextIsEntry ls then unfoldSearch (some l) ls else l :: unfoldSearch none ls

/-- What the classification guarantees: a path is not itself an entry line, an owned line has a
non-empty run of digits and a `:` or `-` separator, and (the side condition) a copied line does not
look like an entry. -/
def WellFormed : SLine → Prop
  | .owned p c n _ => parseEntry p = none ∧ n ≠ [] ∧ (∀ d ∈ n, d.isDigit = true) ∧ (c = ':' ∨ c = '-')
  | .plain l => parseEntry l = none

private theorem digits_split (c : Char) (hc : c.isDigit = false) (rest : Line) :
    ∀ n : Line, (∀ d ∈ n, d.isDigit = true) →
      (n ++ c :: rest).takeWhile Char.isDigit = n ∧ (n ++ c :: rest).dropWhile Char.isDigit = c :: rest
  | [], _ => by simp [hc]
  | d :: ds, h => by
    have hd := h d (List.mem_cons_self ..)
    have ih := digits_split c hc rest ds (fun x hx => h x (List.mem_cons_of_mem _ hx))
    simp [hd, ih.1, ih.2]

private theorem parseEntry_entryLine (c : Char) (n r : Line) (hn : n ≠ []) (hd : ∀ d ∈ n, d.isDigit = true)
    (hc : c = ':' ∨ c = '-') : parseEntry (entryLine c n r) = some (c, n, r) := by
  have hnd : c.isDigit = false := by rcases hc with rfl | rfl <;> decide
  have hs := digits_split c hnd (' ' :: r) n hd
  simp [entryLine, parseEntry, hs.1, hs.2, hn, hc]

private theorem next_after_reset :
    ∀ xs : List SLine, (∀ x ∈ xs, WellFormed x) → nextIsEntry (foldSearch none xs) = false
  | [], _ => rfl
  | .owned p _ _ _ :: _, h => by
    have := (h _ (List.mem_cons_self ..)).1
    simp [foldSearch, nextIsEntry, this]
  | .plain l :: _, h => by
    have : parseEntry l = none := h _ (List.mem_cons_self ..)
    simp [foldSearch, nextIsEntry, this]

private theorem unfold_foldSearch_from :
    ∀ (xs : List SLine) (cur : Option Line), (∀ x ∈ xs, WellFormed x) →
      unfoldSearch cur (foldSearch cur xs) = xs.map SLine.orig
  | [], _, _ => rfl
  | .owned p c n r :: xs, cur, h => by
    have hw : WellFormed (.owned p c n r) := h _ (List.mem_cons_self ..)
    have rest : ∀ x ∈ xs, WellFormed x := fun x hx => h x (List.mem_cons_of_mem _ hx)
    have ih := unfold_foldSearch_from xs (some p) rest
    have hp := parseEntry_entryLine c n r hw.2.1 hw.2.2.1 hw.2.2.2
    by_cases hc : cur = some p
    · subst hc
      simp [foldSearch, unfoldSearch, hp, ih, SLine.orig]
    · simp only [foldSearch, hc, ite_false, List.cons_append, List.nil_append, List.map_cons]
      rw [unfoldSearch, hw.1]
      simp [nextIsEntry, hp, unfoldSearch, ih, SLine.orig]
  | .plain l :: xs, cur, h => by
    have hl : parseEntry l = none := h _ (List.mem_cons_self ..)
    have rest : ∀ x ∈ xs, WellFormed x := fun x hx => h x (List.mem_cons_of_mem _ hx)
    have ih := unfold_foldSearch_from xs none rest
    have hn := next_after_reset xs rest
    simp only [foldSearch, List.map_cons]
    rw [unfoldSearch, hl]
    simp [hn, ih, SLine.orig]

/-- `fold_search` is lossless on well-formed input: unfolding its output gives back every line. -/
theorem unfoldSearch_foldSearch (xs : List SLine) (h : ∀ x ∈ xs, WellFormed x) :
    unfoldSearch none (foldSearch none xs) = xs.map SLine.orig :=
  unfold_foldSearch_from xs none h

/-- `fold_search` as the code runs it now: no fold when a copied line parses as an entry. -/
def foldSearchChecked (xs : List SLine) : Option (List Line) :=
  if xs.any (fun x => match x with
      | .plain l => (parseEntry l).isSome
      | .owned .. => false) then none
  else some (foldSearch none xs)

/-- What the owner classification guarantees (`_SUSPECT_PATH` and `_owner` in the code): an owning
path is not itself an entry line, and an owned line has a run of digits and a `:` or `-`. -/
def OwnedWellFormed : SLine → Prop
  | .owned p c n _ => parseEntry p = none ∧ n ≠ [] ∧ (∀ d ∈ n, d.isDigit = true) ∧ (c = ':' ∨ c = '-')
  | .plain _ => True

/-- `fold_search` is lossless whenever it folds: the refusal supplies the copied-line condition of
`unfoldSearch_foldSearch`, so only the owner classification remains a hypothesis. -/
theorem unfold_foldSearchChecked (xs : List SLine) (out : List Line) (h : foldSearchChecked xs = some out)
    (hw : ∀ x ∈ xs, OwnedWellFormed x) : unfoldSearch none out = xs.map SLine.orig := by
  unfold foldSearchChecked at h
  split at h
  · cases h
  · rename_i hany
    cases h
    apply unfoldSearch_foldSearch
    intro x hx
    cases x with
    | owned p c n r => exact hw _ hx
    | plain l =>
      have := List.any_eq_false.mp (by simpa using hany) _ hx
      simpa [WellFormed] using this

/-- The refusal is necessary: a copied line that looks like an entry makes two different inputs fold
to the same output. On the real function these are `longpath.py:1:a`, `longpath.py:2:b` followed by
either `  3: c` or `longpath.py:3:c`; the code now refuses the first. -/
theorem foldSearch_not_injective :
    ∃ xs ys : List SLine, foldSearch none xs = foldSearch none ys ∧ xs.map SLine.orig ≠ ys.map SLine.orig :=
  ⟨[.owned ['p'] ':' ['1'] ['a'], .plain (entryLine ':' ['2'] ['b'])],
   [.owned ['p'] ':' ['1'] ['a'], .owned ['p'] ':' ['2'] ['b']],
   by decide, by decide⟩

end TokenMasterProofs.Folds
