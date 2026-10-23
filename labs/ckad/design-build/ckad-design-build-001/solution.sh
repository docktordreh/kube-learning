kubectl apply -f - <<'EOF'
apiVersion: batch/v1
kind: CronJob
metadata:
  name: {{cron}}
  namespace: {{ns}}
spec:
  schedule: "*/5 * * * *"
  jobTemplate:
    spec:
      completions: 4
      parallelism: 2
      backoffLimit: 2
      activeDeadlineSeconds: 60
      ttlSecondsAfterFinished: 3600
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: task
              image: docker.io/library/busybox:1.37
              command: ["/bin/sh", "-c", "echo Processing && sleep 5"]
EOF
kubectl -n {{ns}} create job {{cron}}-manual --from=cronjob/{{cron}}
kubectl -n {{ns}} wait --for=condition=Complete job/{{cron}}-manual --timeout=120s
kubectl -n {{ns}} logs job/{{cron}}-manual
