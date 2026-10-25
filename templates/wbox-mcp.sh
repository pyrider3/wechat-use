#!/bin/sh
case "$*" in
  *@HOME@/.config/wbox-mcp/wechat*) exec /usr/bin/python3 @INSTALL@/manual-guard.py "$@" ;;
  *) exec @INSTALL@/wbox-mcp-direct "$@" ;;
esac
