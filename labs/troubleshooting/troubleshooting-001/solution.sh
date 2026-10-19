kubectl -n {{ns}} get pods -l app={{app}}
kubectl -n {{ns}} logs deploy/{{app}} --previous || kubectl -n {{ns}} logs deploy/{{app}}
kubectl -n {{ns}} get configmap {{app}}-config -o jsonpath='{.data}'; echo
# The command reads settings.conf, but the ConfigMap key (and so the file) is settings.env.
# Project the key under the name the program expects:
kubectl -n {{ns}} patch deployment {{app}} --type=json -p '[
  {"op":"add","path":"/spec/template/spec/volumes/0/configMap/items",
   "value":[{"key":"settings.env","path":"settings.conf"}]}]'
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
kubectl -n {{ns}} logs deploy/{{app}}
