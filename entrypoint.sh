#!/bin/bash
set -e

# Function to run the python script
run_script() {
    echo "Running p_art.py script..."
    /usr/local/bin/python /app/p_art.py >> /var/log/cron.log 2>&1
    echo "Script finished."
}

# Run the script on startup
run_script &

# Create log file if it doesn't exist
touch /var/log/cron.log

# Add the cron job
echo "${CRON_SCHEDULE:-0 2 * * *} /usr/local/bin/python /app/p_art.py >> /var/log/cron.log 2>&1" > /etc/cron.d/part-cron

# Give execution rights on the cron job
chmod 0644 /etc/cron.d/part-cron

# Apply cron job
crontab /etc/cron.d/part-cron

# Start cron daemon in foreground and tail the log file
cron -f &
tail -f /var/log/cron.log
