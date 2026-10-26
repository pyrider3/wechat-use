#!/bin/sh
export PATH="@INSTALL@/runtime/usr/bin:$PATH"
export LD_LIBRARY_PATH="@INSTALL@/runtime/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"
exec @INSTALL@/.venv/bin/wbox-mcp "$@"
