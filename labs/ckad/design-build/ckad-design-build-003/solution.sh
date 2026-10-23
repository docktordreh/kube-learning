cd "{{workdir}}/app"
cat Dockerfile
# Default user for every container from this image.
sed -i 's/^CMD /USER 1000\nCMD /' Dockerfile
cat Dockerfile
docker build --tag cka-lab/{{app}}:2.0 .
docker image inspect cka-lab/{{app}}:2.0 --format '{{.Config.User}}'
docker save --output "{{workdir}}/{{app}}-2.0.tar" cka-lab/{{app}}:2.0
cka image load cka-lab/{{app}}:2.0
kubectl -n {{ns}} set image deployment/{{app}} app=cka-lab/{{app}}:2.0
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
kubectl -n {{ns}} exec client -- wget -qO- http://{{app}}
