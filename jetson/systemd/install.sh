#!/bin/sh
# Run on the robot HOST as root:  sudo sh /home/jetbot/sentry/jetson/systemd/install.sh [--with-control]
# Installs the units; estop and camera start now and at every boot. robot_udp (sentry-control) only with --with-control.
set -e
D=$(cd "$(dirname "$0")" && pwd)
cp "$D"/sentry-estop.service "$D"/sentry-camera.service "$D"/sentry-control.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable sentry-estop.service sentry-camera.service
systemctl restart sentry-estop.service sentry-camera.service
if [ "$1" = "--with-control" ]; then
    systemctl enable sentry-control.service
    systemctl restart sentry-control.service
fi
systemctl --no-pager --lines=0 status sentry-estop.service sentry-camera.service || true
