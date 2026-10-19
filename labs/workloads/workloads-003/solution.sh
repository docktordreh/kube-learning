kubectl -n {{ns}} create configmap {{app}}-settings --from-literal=LOG_LEVEL={{level}}
kubectl -n {{ns}} create secret generic {{app}}-db --from-literal=password='{{password}}'
kubectl -n {{ns}} patch deployment {{app}} --type=strategic -p '
spec:
  template:
    spec:
      containers:
        - name: {{app}}
          env:
            - name: LOG_LEVEL
              valueFrom:
                configMapKeyRef:
                  name: {{app}}-settings
                  key: LOG_LEVEL
          volumeMounts:
            - name: db
              mountPath: /etc/{{app}}/db
              readOnly: true
      volumes:
        - name: db
          secret:
            secretName: {{app}}-db
'
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
kubectl -n {{ns}} exec deploy/{{app}} -- sh -c 'printenv LOG_LEVEL; cat /etc/{{app}}/db/password; echo'
