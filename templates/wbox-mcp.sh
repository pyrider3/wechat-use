#!/bin/sh
case "$*" in
  *@HOME@/.config/wbox-mcp/wechat*) exec @INSTALL@/.venv/bin/python @INSTALL@/manual-guard.py "$@" ;;
  *) exec @INSTALL@/wbox-mcp-direct "$@" ;;
esac
