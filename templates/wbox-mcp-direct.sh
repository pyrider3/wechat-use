#!/bin/sh
export PATH="@INSTALL@/runtime/usr/bin:$PATH"
export LD_LIBRARY_PATH="@INSTALL@/runtime/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec @INSTALL@/.venv/bin/wbox-mcp "$@"
