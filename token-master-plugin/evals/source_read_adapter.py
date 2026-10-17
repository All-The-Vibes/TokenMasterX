"""Single-threaded evaluation adapter for executor-observed source reads.

Reuses the original quality tool loop without changing its frozen-study format
or defaults. Use only inside one isolated evaluation process; temporary module
bindings are restored on exit. This is not a native host hook.
"""
from contextlib import contextmanager
from dataclasses import dataclass

from brainspace.request_policy import RequestPolicy, SourceReadInfo
from quality import runner


@dataclass(frozen=True)
class SourceAwareArm(runner.Arm):
    @property
    def policy(self):
        return RequestPolicy(version="request-policy-v2", enabled=self.views, min_tool_chars=512)


@dataclass(frozen=True)
class ConservativeArm(runner.Arm):
    """No implicit task-mode prompt; unique evidence stays unchanged."""
    views: bool = True

    @property
    def policy(self):
        return RequestPolicy(version="request-policy-v3", enabled=self.views, min_tool_chars=512)


_ACTIVE = False


@contextmanager
def executor_source_reads(*, on_plan=None):
    """Collect metadata from real successful reads, never from model claims."""
    global _ACTIVE
    if _ACTIVE:
        raise RuntimeError("source-read evaluation adapter cannot be nested")
    _ACTIVE = True
    actions, execute, prepare = runner._native_actions, runner._execute, runner.prepare_request
    observations = {}
    pending = None

    def observed_actions(body):
        nonlocal pending
        pending = actions(body)
        return pending

    def observed_execute(root, store, name, args, program_runner=None):
        # A failed read raises here; no success observation is manufactured.
        content = execute(root, store, name, args, program_runner)
        # fetch_artifact is a trusted exact-text alias implemented by the
        # parent dispatcher through this same reader. Bind to its visible
        # name, not the implementation name; mismatched outputs fail the hash
        # check in the policy even if a caller wraps the returned text.
        if (name == "read_file" and pending is not None
                and pending[0] in ("read_file", "fetch_artifact")
                and pending[1] == args and type(content) is str):
            try:
                observations[pending[2]] = SourceReadInfo.from_text(
                    call_id=pending[2], tool_name=pending[0], source_path=args["path"],
                    content=content, status="success",
                )
            except (ValueError, TypeError, KeyError):
                pass  # Unsupported metadata cannot authorize an exemption.
        return content

    def observed_prepare(request, policy=None, **options):
        planned = prepare(request, policy, **options, source_reads=tuple(observations.values()))
        if on_plan is not None:
            on_plan(request, planned)
        return planned

    runner._native_actions = observed_actions
    runner._execute = observed_execute
    runner.prepare_request = observed_prepare
    try:
        yield observations
    finally:
        runner._native_actions, runner._execute, runner.prepare_request = actions, execute, prepare
        _ACTIVE = False
