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

end TokenMasterProofs.Routing
