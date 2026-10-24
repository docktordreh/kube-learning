# The warnings name every violation of the existing Pods.
kubectl label namespace {{ns}} pod-security.kubernetes.io/enforce=restricted --overwrite
kubectl -n {{ns}} patch deployment {{app}} --type=strategic -p '
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: web
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
'
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
kubectl -n {{ns}} exec client -- wget -qO- http://{{app}}
