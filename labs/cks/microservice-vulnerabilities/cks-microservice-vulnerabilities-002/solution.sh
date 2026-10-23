kubectl -n {{ns}} patch deployment {{app}} --type=strategic -p '
spec:
  template:
    spec:
      containers:
        - name: web
          env: null
          volumeMounts:
            - name: app-secret
              mountPath: /run/secrets/app
              readOnly: true
      volumes:
        - name: app-secret
          secret:
            secretName: {{secret}}
            defaultMode: 0400
'
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
kubectl -n {{ns}} exec client -- wget -qO- http://{{app}}
