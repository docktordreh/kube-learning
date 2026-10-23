kubectl -n {{ns}} get pod {{app}} -o jsonpath='{.spec.containers[*].name}'; echo
kubectl -n {{ns}} logs {{app}} --all-containers --prefix | grep ERROR | head -n 3
echo {{bad}} > {{workdir}}/container.txt
kubectl -n {{ns}} logs {{app}} -c {{bad}} | grep ERROR > {{workdir}}/errors.log
wc -l {{workdir}}/errors.log
