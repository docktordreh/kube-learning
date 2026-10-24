kubectl -n {{ns}} create serviceaccount {{sa}}
kubectl -n {{ns}} create role {{sa}} \
  --verb=get,list,watch,create,update,patch,delete --resource=deployments.apps
# A second rule for Pods and their logs (kubectl create role allows one verb set per call,
# so append it with a patch).
kubectl -n {{ns}} patch role {{sa}} --type=json -p '[{"op":"add","path":"/rules/-","value":{"apiGroups":[""],"resources":["pods","pods/log"],"verbs":["get","list","watch"]}}]'
kubectl -n {{ns}} create rolebinding {{sa}} --role={{sa}} --serviceaccount={{ns}}:{{sa}}
# Verify.
kubectl auth can-i delete deployments -n {{ns}} --as=system:serviceaccount:{{ns}}:{{sa}}
kubectl auth can-i get pods --subresource=log -n {{ns}} --as=system:serviceaccount:{{ns}}:{{sa}}
kubectl auth can-i get secrets -n {{ns}} --as=system:serviceaccount:{{ns}}:{{sa}} || true
