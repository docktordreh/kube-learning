kubectl -n {{ns}} patch deployment {{app}} --type=strategic -p '
spec:
  template:
    spec:
      securityContext:
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: agent
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
'
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
kubectl -n {{ns}} exec deploy/{{app}} -- grep -E '^(CapEff|NoNewPrivs|Seccomp):' /proc/1/status
