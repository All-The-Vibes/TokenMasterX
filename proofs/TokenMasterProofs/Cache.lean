/-!
# Cache safety of the BYOK bridge

Source: `rewrite_request` in `token-master-plugin/skills/token-master/brainspace_copilot_bridge.py`,
which applies `stable_session_prefix` and then `shape_tool_result` to every request.

Copilot CLI resends the whole history on every call, and the provider caches exact prompt
prefixes. A call reads the earlier part of its prompt from the cache only if that part is the same
bytes as before. The bridge moves the session folder line into the first user message, then shapes
each tool output using the name and arguments of the call with the same id. Python keeps those calls
in a dict, so the last call with an id wins.

Assumptions: the client sends the same instructions and tool list on every call of a session (the
tool list is fixed by `--excluded-tools` at launch, and a resume that the launcher ties to the
session's record passes the recorded list again, `Routing.resume_same_list`; other resumes, and
`--all-tools` or `TOKENMASTER_KEEP_TOOLS` on a resume, may change it), a new item never reuses an id
the earlier history mentions, and `shape` is a total function: the code's token counter raises on a
lone surrogate, and then the bridge fails the call. proofs/README.md says which of these the
conformance tests check.
-/
namespace TokenMasterProofs.Cache

/-- The input items the bridge reads. -/
inductive Item where
  | call (id : Nat) (name args : String)
  | output (id : Nat) (body : String)
  | user (text : String)
  | other (data : String)

/-- The call id an item mentions, if any. -/
def Item.id? : Item → Option Nat
  | .call i _ _ => some i
  | .output i _ => some i
  | _ => none

/-- The (name, arguments) of every call with id `i`, in order. -/
def callsWith (i : Nat) (h : List Item) : List (String × String) :=
  h.filterMap fun
    | .call j n a => if j = i then some (n, a) else none
    | _ => none

/-- `calls[call_id]` in `rewrite_request`: the last call with that id. -/
def lookup (h : List Item) (i : Nat) : Option (String × String) := (callsWith i h).getLast?

/-- Shape one item. `shape` is `shape_tool_result` with the session's counter, extended by the
identity for tools of kind "other" and for unreadable arguments: some function of (name, arguments,
output) and nothing else. -/
def shapeItem (shape : String → String → String → String) (lk : Nat → Option (String × String)) :
    Item → Item
  | .output i b =>
    match lk i with
    | some (n, a) => .output i (shape n a b)
    | none => .output i b
  | x => x

/-- Prepend the folder header to the first user message (`stable_session_prefix`). -/
def prependFirstUser (hdr : String) : List Item → List Item
  | [] => []
  | .user t :: xs => .user (hdr ++ t) :: xs
  | .call i n a :: xs => .call i n a :: prependFirstUser hdr xs
  | .output i b :: xs => .output i b :: prependFirstUser hdr xs
  | .other d :: xs => .other d :: prependFirstUser hdr xs

/-- `rewrite_request` on the input items. -/
def bridge (shape : String → String → String → String) (hdr : String) (h : List Item) : List Item :=
  (prependFirstUser hdr h).map (shapeItem shape (lookup (prependFirstUser hdr h)))

/-- The new items reuse no id the earlier history mentions. -/
def Fresh (h e : List Item) : Prop :=
  ∀ y ∈ h, ∀ i, y.id? = some i → ∀ n a, Item.call i n a ∉ e

def HasUser (h : List Item) : Prop := ∃ t, Item.user t ∈ h

private theorem prependFirstUser_append (hdr : String) :
    ∀ (h e : List Item), HasUser h → prependFirstUser hdr (h ++ e) = prependFirstUser hdr h ++ e
  | [], _, ⟨_, ht⟩ => absurd ht List.not_mem_nil
  | .user t :: xs, e, _ => rfl
  | .call i n a :: xs, e, ⟨u, hu⟩ => by
    have : HasUser xs := ⟨u, by simpa using hu⟩
    simp [prependFirstUser, prependFirstUser_append hdr xs e this]
  | .output i b :: xs, e, ⟨u, hu⟩ => by
    have : HasUser xs := ⟨u, by simpa using hu⟩
    simp [prependFirstUser, prependFirstUser_append hdr xs e this]
  | .other d :: xs, e, ⟨u, hu⟩ => by
    have : HasUser xs := ⟨u, by simpa using hu⟩
    simp [prependFirstUser, prependFirstUser_append hdr xs e this]

private theorem mem_prependFirstUser (hdr : String) :
    ∀ (h : List Item) (y : Item), y ∈ prependFirstUser hdr h → y ∈ h ∨ ∃ t, y = .user t
  | [], _, hy => absurd hy List.not_mem_nil
  | .user t :: xs, y, hy => by
    rcases List.mem_cons.mp hy with rfl | hy
    · exact Or.inr ⟨_, rfl⟩
    · exact Or.inl (List.mem_cons_of_mem _ hy)
  | .call i n a :: xs, y, hy => by
    rcases List.mem_cons.mp hy with rfl | hy
    · exact Or.inl (List.mem_cons_self ..)
    · exact (mem_prependFirstUser hdr xs y hy).imp (List.mem_cons_of_mem _) id
  | .output i b :: xs, y, hy => by
    rcases List.mem_cons.mp hy with rfl | hy
    · exact Or.inl (List.mem_cons_self ..)
    · exact (mem_prependFirstUser hdr xs y hy).imp (List.mem_cons_of_mem _) id
  | .other d :: xs, y, hy => by
    rcases List.mem_cons.mp hy with rfl | hy
    · exact Or.inl (List.mem_cons_self ..)
    · exact (mem_prependFirstUser hdr xs y hy).imp (List.mem_cons_of_mem _) id

private theorem callsWith_append (i : Nat) (a b : List Item) :
    callsWith i (a ++ b) = callsWith i a ++ callsWith i b := by
  simp [callsWith, List.filterMap_append]

private theorem callsWith_fresh (i : Nat) :
    ∀ e : List Item, (∀ n a, Item.call i n a ∉ e) → callsWith i e = []
  | [], _ => rfl
  | x :: xs, h => by
    have rest := callsWith_fresh i xs (fun n a m => h n a (List.mem_cons_of_mem _ m))
    cases x with
    | call j n a =>
      by_cases hj : j = i
      · subst hj
        exact absurd (List.mem_cons_self ..) (h n a)
      · simp [callsWith, hj] at rest ⊢
        exact rest
    | output j b => simpa [callsWith] using rest
    | user t => simpa [callsWith] using rest
    | other d => simpa [callsWith] using rest

/-- The shaping map alone: every output shaped from the call with its id, nothing else changed. This
is what `plan_v6_request` applies to a chat request's tool messages, and what the bridge applies after
moving the folder line. -/
def shaping (shape : String → String → String → String) (h : List Item) : List Item :=
  h.map (shapeItem shape (lookup h))

/-- If a history extends an earlier one, and the new items reuse no id the earlier history mentions,
shaping the earlier history gives a prefix of shaping the new one: no earlier message changes. -/
theorem shaping_prefix_stable (shape : String → String → String → String) (h e : List Item)
    (hf : Fresh h e) : shaping shape h <+: shaping shape (h ++ e) := by
  unfold shaping
  rw [List.map_append]
  have same : h.map (shapeItem shape (lookup (h ++ e))) = h.map (shapeItem shape (lookup h)) := by
    apply List.map_congr_left
    intro x hx
    cases x with
    | output i b =>
      have hnone : callsWith i e = [] := callsWith_fresh i e (hf _ hx i rfl)
      have hl : lookup (h ++ e) i = lookup h i := by
        simp only [lookup, callsWith_append, hnone, List.append_nil]
      simp only [shapeItem, hl]
    | call i n a => rfl
    | user t => rfl
    | other d => rfl
  rw [same]
  exact List.prefix_append _ _

private theorem fresh_prepend (hdr : String) (h e : List Item) (hf : Fresh h e) :
    Fresh (prependFirstUser hdr h) e := by
  intro y hy i hi
  rcases mem_prependFirstUser hdr h y hy with hy | ⟨t, rfl⟩
  · exact hf y hy i hi
  · simp [Item.id?] at hi

/-- If a call's history extends the previous call's, and the new items reuse no id the earlier
history mentions, the bridge's rewrite of the previous history is a prefix of its rewrite of the
new one. Every byte the provider cached for the previous call is sent again unchanged. -/
theorem bridge_prefix_stable (shape : String → String → String → String) (hdr : String)
    (h e : List Item) (hu : HasUser h) (hf : Fresh h e) :
    bridge shape hdr h <+: bridge shape hdr (h ++ e) := by
  have := shaping_prefix_stable shape (prependFirstUser hdr h) e (fresh_prepend hdr h e hf)
  unfold bridge
  rw [prependFirstUser_append hdr h e hu]
  exact this

/-- The serialized items: the first item's encoding, then each later item with its leading comma. -/
def body {τ : Type} (encFirst encRest : Item → List τ) : List Item → List τ
  | [] => []
  | x :: xs => encFirst x ++ (xs.map encRest).flatten

private theorem body_prefix {τ : Type} (encFirst encRest : Item → List τ) (a b : List Item)
    (hp : a <+: b) : body encFirst encRest a <+: body encFirst encRest b := by
  obtain ⟨t, rfl⟩ := hp
  cases a with
  | nil => exact List.nil_prefix
  | cons x xs =>
    refine ⟨(t.map encRest).flatten, ?_⟩
    simp [body, List.map_append, List.flatten_append, List.append_assoc]

/-- With the same header (instructions and tools) on every call, the previous request, up to the
end of its last item, is a prefix of the next request: the provider can serve all of it from cache. -/
theorem cache_prefix_kept {τ : Type} (header : List τ) (encFirst encRest : Item → List τ)
    (shape : String → String → String → String) (hdr : String) (h e : List Item)
    (hu : HasUser h) (hf : Fresh h e) :
    header ++ body encFirst encRest (bridge shape hdr h)
      <+: header ++ body encFirst encRest (bridge shape hdr (h ++ e)) := by
  obtain ⟨t, ht⟩ := body_prefix encFirst encRest _ _ (bridge_prefix_stable shape hdr h e hu hf)
  exact ⟨t, by rw [List.append_assoc, ht]⟩

end TokenMasterProofs.Cache
