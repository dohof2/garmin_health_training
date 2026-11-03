# Garmin & sync / Synchronization

Inspect current status and affected checkpoints first. The existing Sync UI owns starting/retrying sync and authentication, including MFA. Use open_app_workflow to provide the exact existing control; do not claim a job started from a read. Diagnose from recorded status rather than credentials, logs or guesses. Never trigger a second sync if one is running.
