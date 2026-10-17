# Windows isolation feasibility — G08 remains unqualified

October 8, 2026. This was a bounded official-documentation review, not an OS
experiment. No profile, ACL, network exemption, credential store or application
was changed or launched.

## Decision

Do not launch the pinned Codex CLI/Desktop merely by changing `CODEX_HOME` or
by assuming an AppContainer wrapper supplies the required complete boundary.

Microsoft documents AppContainer/LPAC as genuine process isolation. It does not
establish that the specific Codex executable/helper tree will operate inside
the needed capability/file/network allowlist as an ordinary user.

- Profile creation and launch are documented through current-user APIs, but
  access may be denied. The documentation does not justify either a blanket
  admin requirement or an assumption that this host/application will work.
- Filesystem, registry, credential and inherited-handle boundaries require
  explicit configuration and verification. LPAC removes additional implicit
  access; broad grants must not replace the intended private boundary.
- The documented ordinary AppContainer-to-unpackaged-host loopback path needs
  an administrator-enabled exemption. That conflicts with the current
  no-admin/no-exemption-change boundary for the existing mock HTTP provider.
- Packaged-to-packaged IPC is a different configuration, not proof that the
  existing Codex/mock pair works. It was not implemented or tested.
- Electron Desktop compatibility for the entire process/helper/IPC/GPU tree
  remains unknown. Packaging by itself is not equivalent to sandboxing.
- AppContainer profiles have persistent per-user storage and explicit cleanup;
  they are not automatically disposable VMs.

Codex's built-in command sandbox is not proof of whole-harness/Desktop isolation
from the normal user's configuration, skills or OS credential storage.

## Required before a future native launch

1. Exact executable/helper versions, hashes, Windows build and supported launch
   mechanism.
2. A checked SID/capability/ACL policy covering the complete process tree and
   all inherited handles, without normal-profile or broad-package grants.
3. A clean explicit environment and independent state/credential separation.
4. A mock-provider route satisfying the unchanged isolation requirement.
5. Exact owned-resource termination/deletion and evidence that normal settings
   remain unchanged.

The current evidence supplies none of the missing live acceptance cells.
Native Windows/Desktop remains a real qualification gap, not a test that can
be marked passed from Linux results or documentation.

## Primary references reviewed

```text
https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer
https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-createappcontainerprofile
https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation
https://learn.microsoft.com/en-us/windows/apps/develop/communication/interprocess-communication#loopback
https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-deleteappcontainerprofile
https://learn.microsoft.com/en-us/windows/msix/msix-container
https://developers.openai.com/codex/windows
https://developers.openai.com/codex/config-advanced
https://openai.com/index/building-codex-windows-sandbox/
```
