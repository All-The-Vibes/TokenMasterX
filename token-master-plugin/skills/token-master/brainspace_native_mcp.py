#!/usr/bin/env python
"""Task-owned native recovery MCP; explicitly supplied local control only."""
import os
import sys

from brainspace.native_mcp import NativeRecoveryClient, make_server


def main():
    try:
        client = NativeRecoveryClient(
            base_url=os.environ["TOKENMASTER_NATIVE_CONTROL_URL"],
            token=os.environ["TOKENMASTER_NATIVE_CONTROL_TOKEN"],
        )
        make_server(client).run()
        return 0
    except Exception as error:
        # Never include an endpoint credential, native source or exception text.
        sys.stderr.write("native_recovery_server_failed:" + type(error).__name__ + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
