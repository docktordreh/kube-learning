In namespace `{{ns}}`, create a CronJob `{{cron}}`:

- It runs every 5 minutes.
- Its container runs `docker.io/library/busybox:1.37` with the command
  `/bin/sh -c "echo Processing && sleep 5"`.
- Each Job needs **4** successful Pods, runs at most **2** Pods in parallel,
  retries failed Pods at most **2** times, fails when it runs longer than
  **60 seconds**, and is deleted automatically **1 hour** after it finishes.
- The Pods' `restartPolicy` is `Never`.

Then trigger the CronJob once right away: create a Job `{{cron}}-manual` from
it and let it finish.
