## CronJob, Job and Pod: three layers

A CronJob creates a Job at every schedule tick (`*/5 * * * *` = minute 0, 5,
10, ...). The Job creates Pods until enough of them succeeded. Each layer has
its own settings:

| setting                         | layer   | effect                                                       |
|---------------------------------+---------+--------------------------------------------------------------|
| `schedule`, `concurrencyPolicy` | CronJob | when Jobs start and whether runs may overlap                 |
| `completions`                   | Job     | successful Pods needed (4)                                   |
| `parallelism`                   | Job     | Pods running at once (2, so two waves here)                  |
| `backoffLimit`                  | Job     | failed Pods tolerated before the Job fails                   |
| `activeDeadlineSeconds`         | Job     | wall-clock limit for the whole Job, retries included         |
| `ttlSecondsAfterFinished`       | Job     | the TTL controller deletes the finished Job and its Pods     |
| `restartPolicy`                 | Pod     | `Never` or `OnFailure` (Jobs reject `Always`)                |

With `restartPolicy: Never`, every failure creates a new Pod, so failed Pods
stay visible for debugging. `OnFailure` restarts the container in place
instead.

`kubectl create job --from=cronjob/<name>` copies the CronJob's job template
into a new Job and marks it with the annotation
`cronjob.kubernetes.io/instantiate: manual`. It is the standard way to test a
CronJob without waiting for its schedule.

## How to recognise problems in production

- Job `DeadlineExceeded`: the deadline covers the whole Job, so sequential
  waves (completions / parallelism × runtime) must fit inside it. The original
  scenario this lab is based on asked for 4 × 30 s at parallelism 2 within 40 s,
  which can never succeed.
- Job `BackoffLimitExceeded`: inspect the failed Pods' logs; with `OnFailure`
  look at container restart counts instead.
- A very short `ttlSecondsAfterFinished` deletes Jobs before anyone reads
  their logs. Keep it long enough for your log shipping.
- Missed schedules after controller downtime start only within
  `startingDeadlineSeconds`.

## Alternatives

- `kubectl create cronjob ... --dry-run=client -o yaml` plus editing the
  generated file is usually fastest in an exam.
- `successfulJobsHistoryLimit` and `failedJobsHistoryLimit` limit how many
  finished Jobs a CronJob keeps, instead of a TTL.
