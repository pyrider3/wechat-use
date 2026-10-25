#!/bin/sh
systemctl --user start wbox-wechat-silent.service
task_audio_ready=0
for task_audio_attempt in 1 2 3 4 5 6 7 8 9 10; do
    if pactl list short sinks | cut -f2 | /usr/bin/grep -qx wbox_wechat_silent; then task_audio_ready=1; break; fi
    sleep 0.2
done
[ "$task_audio_ready" = 1 ] || exit 1
exec bwrap --die-with-parent --ro-bind / / --dev-bind /dev /dev --proc /proc --bind @INSTALL@/wechat-profile @HOME@ --bind @RUNTIME@ @RUNTIME@ --tmpfs /tmp --ro-bind /tmp/.X11-unix /tmp/.X11-unix --chdir @HOME@ /usr/bin/env -u LD_LIBRARY_PATH -u QT_PLUGIN_PATH -u QT_QPA_PLATFORM_PLUGIN_PATH PULSE_SINK=wbox_wechat_silent /usr/bin/dbus-run-session -- /opt/wechat/wechat
