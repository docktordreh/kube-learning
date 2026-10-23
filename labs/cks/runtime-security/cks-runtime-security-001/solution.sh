# Read-only root plus a writable emptyDir for the path the app writes to.
kubectl -n {{ns}} patch deployment {{app}} --type=strategic -p '
spec:
  template:
    spec:
      containers:
        - name: web
          securityContext:
            readOnlyRootFilesystem: true
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir: {}
'
# Strategic merge cannot delete a field by omission; set privileged to false explicitly.
kubectl -n {{ns}} patch deployment {{debug}} --type=strategic -p '
spec:
  template:
    spec:
      containers:
        - name: toolbox
          securityContext:
            privileged: false
            readOnlyRootFilesystem: true
'
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
kubectl -n {{ns}} rollout status deployment/{{debug}} --timeout=120s
kubectl -n {{ns}} exec client -- wget -qO- http://{{app}}
