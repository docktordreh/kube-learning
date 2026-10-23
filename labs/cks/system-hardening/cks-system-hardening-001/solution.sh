cka node exec {{node.worker1}} <<'EOF'
set -eu
grep "^profile" /etc/apparmor.d/cka-{{profile}}
apparmor_parser --replace /etc/apparmor.d/cka-{{profile}}
grep '^{{profile}} ' /sys/kernel/security/apparmor/profiles
EOF
# The profile name (from the file), not the file name.
kubectl -n {{ns}} patch deployment {{app}} --type=strategic -p '
spec:
  template:
    spec:
      containers:
        - name: agent
          securityContext:
            appArmorProfile:
              type: Localhost
              localhostProfile: {{profile}}
'
kubectl -n {{ns}} rollout status deployment/{{app}} --timeout=120s
kubectl -n {{ns}} exec deploy/{{app}} -- cat /proc/1/attr/apparmor/current
kubectl -n {{ns}} exec deploy/{{app}} -- touch /etc/test || echo "denied as expected"
