"""Brainspace: conservative views, scoped recovery and token-only evaluation.

Graph navigation and content views can reduce overlapping traffic; their gains
must be measured together, not assumed to multiply. Runtime transforms are
explicit, offline by default and guarded on the complete reference-token view.
A matching original in storage is not a task-quality or efficiency certificate.

Public modules:
  router: intent-aware guarded text transformations.
  ccr: workspace/session-scoped exact originals, paging and search.
  tokens: pinned offline reference counter; estimates are diagnostic only.
  pipeline/request_policy: explicit protected whole-request planning.
  token_ledger/certification/optimizer: complete traces and independent gates.
  jev: optional advisory typed decisions; no authority or model-weight updates.
  task_mode: explicit task/session contracts, not guaranteed model obedience.

Tools safely retain input when unavailable. Optimizer proof obligations instead
reject invalid/incomplete evidence. Host interception is adapter-specific; no
module claims universal capture or unknown internal tokens equal zero.
"""

__all__ = ["__version__"]
__version__ = "0.3.0"
