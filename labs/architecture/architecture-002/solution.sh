kubectl create clusterrole {{role}} --verb=get,list,watch \
  --resource=nodes,persistentvolumes,storageclasses.storage.k8s.io
kubectl create clusterrolebinding {{role}} --clusterrole={{role}} --group={{group}}
kubectl auth can-i list nodes --as={{user}} --as-group={{group}}
kubectl auth can-i patch nodes --as={{user}} --as-group={{group}} || true
