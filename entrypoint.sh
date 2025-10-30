#!/bin/bash
set -e

# Create log file
touch /var/log/cron.log

# Add the cron job
echo "${CRON_SCHEDULE:-0 2 * * *} /usr/local/bin/python /app/p_art.py >> /var/log/cron.log 2>&1" > /etc/cron.d/part-cron

# Give execution rights on the cron job
chmod 0644 /etc/cron.d/part-cron

# Apply cron job
crontab /etc/cron.d/part-cron

# Start cron daemon in foreground
cron -f
