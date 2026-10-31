/-!
# Tool routing

Source: `select_excluded_tools` and `CAPABILITY_GROUPS` in
`token-master-plugin/skills/token-master/brainspace_copilot_bridge.py`.

The launcher starts Copilot CLI with `--excluded-tools` set to the auxiliary tools a session
does not need. `LEAN_EXCLUDED_TOOLS` is every family's tools in source order, and
`select_excluded_tools` removes from it every tool in a `keep` set built from the prompt, the
flags, installed skill and agent names, and `TOKENMASTER_KEEP_TOOLS`.

The model keeps the families and the filter exact. Which families fire is a parameter: the
regular expressions, flag parsing and installed-name lookup are covered by the conformance tests.

A launch that resumes a session sends the list recorded for the session instead (`recorded_tools`
in `lean_command`). Which record applies is a parameter too: the conformance tests cover the lookup.
-/
namespace TokenMasterProofs.Routing

/-- Copilot CLI's core coding tools and every tool in `CAPABILITY_GROUPS`. -/
inductive Tool where
  | view | edit | create | rg | glob | powershell | report_intent
  | session_store_sql
  | task | read_agent | write_agent | list_agents
  | skill
  | sql
  | read_powershell | stop_powershell | list_powershell
  | fetch_copilot_cli_documentation
  | run_dynamic_workflow | dynamic_workflows_manage
  deriving DecidableEq, Repr

/-- The families of `CAPABILITY_GROUPS`, in source order. -/
inductive Group where
  | session_history | agents | skills | sql | background_shell | copilot_docs | workflows
  deriving DecidableEq, Repr

def Group.all : List Group :=
  [.session_history, .agents, .skills, .sql, .background_shell, .copilot_docs, .workflows]

def Group.tools : Group → List Tool
  | .session_history => [.session_store_sql]
  | .agents => [.task, .read_agent, .write_agent, .list_agents]
  | .skills => [.skill]
  | .sql => [.sql]
  | .background_shell => [.read_powershell, .stop_powershell, .list_powershell]
  | .copilot_docs => [.fetch_copilot_cli_documentation]
  | .workflows => [.run_dynamic_workflow, .dynamic_workflows_manage]

/-- `LEAN_EXCLUDED_TOOLS`. -/
def leanExcluded : List Tool := Group.all.flatMap Group.tools

/-- The tools the bridge's comment says are always kept. -/
def core : List Tool := [.view, .edit, .create, .rg, .glob, .powershell, .report_intent]

/-- What `select_excluded_tools` reads: which families fired (a prompt pattern, `--agent`,
`--resume` or `--continue`, an installed skill or agent name in the prompt) and the tools
`TOKENMASTER_KEEP_TOOLS` names, directly or by their family's name. -/
structure Signals where
  fires : Group → Bool
  env : List Tool

/-- `keep` before the skill rule. -/
def keep₀ (s : Signals) : List Tool := s.env ++ (Group.all.filter s.fires).flatMap Group.tools

/-- `keep`: a kept `skill` tool also keeps the workflow tools and the subagent tools, since a skill may start a
workflow or hand work to a subagent. -/
def keep (s : Signals) : List Tool :=
  if Tool.skill ∈ keep₀ s then keep₀ s ++ Group.tools .workflows ++ Group.tools .agents else keep₀ s

/-- `select_excluded_tools`: the lean list without anything kept, in order. -/
def excluded (s : Signals) : List Tool := leanExcluded.filter (fun t => decide (t ∉ keep s))

private theorem core_disjoint : ∀ t ∈ core, t ∉ leanExcluded := by decide

private theorem every_group_listed (g : Group) : g ∈ Group.all := by cases g <;> decide

private theorem keep₀_sub_keep (s : Signals) {t : Tool} (h : t ∈ keep₀ s) : t ∈ keep s := by
  unfold keep
  split <;> simp [h]

private theorem keep_of_skill (s : Signals) (h : Tool.skill ∈ keep₀ s) :
    keep s = keep₀ s ++ Group.tools .workflows ++ Group.tools .agents := by
  simp [keep, h]

/-- Routing only removes tools from `LEAN_EXCLUDED_TOOLS`; it never excludes anything else. -/
theorem excluded_subset_lean (s : Signals) : ∀ t ∈ excluded s, t ∈ leanExcluded :=
  fun _ ht => (List.mem_filter.mp ht).1

/-- No core coding tool is ever excluded, whatever the prompt and flags. -/
theorem core_never_excluded (s : Signals) : ∀ t ∈ core, t ∉ excluded s :=
  fun t ht hex => core_disjoint t ht (excluded_subset_lean s t hex)

/-- A kept tool is not excluded. -/
theorem kept_not_excluded (s : Signals) {t : Tool} (h : t ∈ keep s) : t ∉ excluded s := by
  intro hex
  have := (List.mem_filter.mp hex).2
  simp [h] at this

/-- If a family's trigger fires, none of its tools is excluded. -/
theorem fired_family_kept (s : Signals) {g : Group} (hg : s.fires g = true) :
    ∀ t ∈ g.tools, t ∉ excluded s := by
  intro t ht
  apply kept_not_excluded
  apply keep₀_sub_keep
  unfold keep₀
  exact List.mem_append_right _
    (List.mem_flatMap.mpr ⟨g, List.mem_filter.mpr ⟨every_group_listed g, hg⟩, ht⟩)

/-- A tool named in `TOKENMASTER_KEEP_TOOLS` is not excluded. -/
theorem env_tool_kept (s : Signals) {t : Tool} (h : t ∈ s.env) : t ∉ excluded s :=
  kept_not_excluded s (keep₀_sub_keep s (List.mem_append_left _ h))

/-- Keeping `skill` keeps both workflow tools. -/
theorem workflows_follow_skill (s : Signals) (h : Tool.skill ∈ keep₀ s) :
    Tool.run_dynamic_workflow ∉ excluded s ∧ Tool.dynamic_workflows_manage ∉ excluded s := by
  constructor <;> apply kept_not_excluded <;> rw [keep_of_skill s h] <;> simp [Group.tools]

/-- Keeping `skill` keeps the four subagent tools. -/
theorem agents_follow_skill (s : Signals) (h : Tool.skill ∈ keep₀ s) :
    ∀ t ∈ Group.tools .agents, t ∉ excluded s := by
  intro t ht
  apply kept_not_excluded
  rw [keep_of_skill s h]
  exact List.mem_append_right _ ht

/-- With no signal at all, the whole lean list is excluded. -/
theorem nothing_fires_excludes_all (s : Signals) (hf : ∀ g, s.fires g = false) (he : s.env = []) :
    excluded s = leanExcluded := by
  have h0 : keep₀ s = [] := by
    simp [keep₀, he, hf]
  have hk : keep s = [] := by simp [keep, h0]
  simp [excluded, hk]

/-- The signals of a launch with no prompt and no flags: `TOKENMASTER_KEEP_TOOLS` alone. -/
def envOnly (s : Signals) : Signals := ⟨fun _ => false, s.env⟩

/-- `lean_command` for a routed launch that resumes a session: the list the launcher last gave the session, less what
the resume's `TOKENMASTER_KEEP_TOOLS` alone keeps (which also drops anything outside `LEAN_EXCLUDED_TOOLS`), or, with
no record, the list routed from the resume's own prompt and flags. `--all-tools` and the user's own tool flags skip
routing, and the model does not cover them. -/
def resumed (recorded : Option (List Tool)) (s : Signals) : List Tool :=
  match recorded with
  | some l => l.filter (fun t => decide (t ∈ excluded (envOnly s)))
  | none => excluded s

/-- A resume excludes nothing outside `LEAN_EXCLUDED_TOOLS`, whatever was recorded. -/
theorem resumed_subset_lean (r : Option (List Tool)) (s : Signals) : ∀ t ∈ resumed r s, t ∈ leanExcluded := by
  cases r with
  | none => exact excluded_subset_lean s
  | some l => exact fun t ht => excluded_subset_lean _ t (of_decide_eq_true (List.mem_filter.mp ht).2)

/-- No core coding tool is excluded on a resume either. -/
theorem resumed_core_never_excluded (r : Option (List Tool)) (s : Signals) : ∀ t ∈ core, t ∉ resumed r s :=
  fun t ht hex => core_disjoint t ht (resumed_subset_lean r s t hex)

/-- A tool named in the resume's `TOKENMASTER_KEEP_TOOLS` is not excluded, whatever was recorded. -/
theorem resumed_env_kept (r : Option (List Tool)) (s : Signals) {t : Tool} (h : t ∈ s.env) : t ∉ resumed r s := by
  cases r with
  | none => exact env_tool_kept s h
  | some l => exact fun ht => env_tool_kept (envOnly s) h (of_decide_eq_true (List.mem_filter.mp ht).2)

/-- With no record, a resume is routed like any launch. -/
theorem resume_without_record (s : Signals) : resumed none s = excluded s := rfl

/-- What `TOKENMASTER_KEEP_TOOLS` alone keeps, a launch whose own `TOKENMASTER_KEEP_TOOLS` names at least those tools
keeps too. -/
private theorem envOnly_keep_sub (s₀ s : Signals) (h : ∀ t ∈ s.env, t ∈ s₀.env) :
    ∀ t ∈ keep (envOnly s), t ∈ keep s₀ := by
  have h0 : keep₀ (envOnly s) = s.env := by simp [keep₀, envOnly]
  intro t ht
  unfold keep at ht
  split at ht
  · rename_i hs
    rw [h0] at hs ht
    rw [keep_of_skill s₀ (List.mem_append_left _ (h _ hs))]
    simp only [List.mem_append] at ht ⊢
    rcases ht with (ht | ht) | ht
    · exact Or.inl (Or.inl (List.mem_append_left _ (h t ht)))
    · exact Or.inl (Or.inr ht)
    · exact Or.inr ht
  · rw [h0] at ht
    exact keep₀_sub_keep s₀ (List.mem_append_left _ (h t ht))

/-- A resume of a session whose first launch's list is recorded sends that list again, whatever prompt and routing
flags the resume has, as long as its `TOKENMASTER_KEEP_TOOLS` names nothing the first launch's did not. -/
theorem resume_same_list (s₀ s : Signals) (h : ∀ t ∈ s.env, t ∈ s₀.env) :
    resumed (some (excluded s₀)) s = excluded s₀ := by
  apply List.filter_eq_self.mpr
  intro t ht
  have hnot : t ∉ keep s₀ := of_decide_eq_true (List.mem_filter.mp ht).2
  exact decide_eq_true (List.mem_filter.mpr ⟨excluded_subset_lean s₀ t ht,
    decide_eq_true fun hk => hnot (envOnly_keep_sub s₀ s h t hk)⟩)

/-- Any number of resumes that the launcher ties to the session, each given the list the launch before it recorded,
all send the first launch's list, as long as none of their `TOKENMASTER_KEEP_TOOLS` names more than the first's. -/
theorem resume_chain_keeps_first_list (s₀ : Signals) (resumes : List Signals)
    (h : ∀ s ∈ resumes, ∀ t ∈ s.env, t ∈ s₀.env) :
    resumes.foldl (fun l s => resumed (some l) s) (excluded s₀) = excluded s₀ := by
  induction resumes with
  | nil => rfl
  | cons s rest ih =>
    simp only [List.foldl, resume_same_list s₀ s (h s (List.mem_cons_self ..))]
    exact ih fun s' hs' => h s' (List.mem_cons_of_mem _ hs')

end TokenMasterProofs.Routing
