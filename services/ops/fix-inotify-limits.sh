#!/bin/bash
# Fix inotify limits for cAdvisor
# Run with: sudo ./fix-inotify-limits.sh

echo "Current inotify limits:"
echo "  max_user_instances: $(cat /proc/sys/fs/inotify/max_user_instances)"
echo "  max_user_watches: $(cat /proc/sys/fs/inotify/max_user_watches)"
echo ""

echo "Increasing inotify limits..."
sysctl -w fs.inotify.max_user_instances=512
sysctl -w fs.inotify.max_user_watches=524288

echo ""
echo "New inotify limits:"
echo "  max_user_instances: $(cat /proc/sys/fs/inotify/max_user_instances)"
echo "  max_user_watches: $(cat /proc/sys/fs/inotify/max_user_watches)"
echo ""

echo "Making changes persistent across reboots..."
echo "fs.inotify.max_user_instances = 512" >> /etc/sysctl.conf
echo "fs.inotify.max_user_watches = 524288" >> /etc/sysctl.conf

echo "Done! Now restart cAdvisor:"
echo "  docker compose -f services/ops/docker-compose.monitoring.yml restart"
