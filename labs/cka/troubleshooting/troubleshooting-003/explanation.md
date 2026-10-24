## What was wrong

Each Pod requested `{{cpu}}` CPUs. The scheduler places a Pod only on a node
whose **allocatable** capacity minus the sum of the **requests** already placed
there covers the new Pod's requests. Actual usage does not matter. No node
had {{cpu}} CPUs, so the Pods stayed `Pending` with
`0/3 nodes are available: 3 Insufficient cpu`.

## Reading FailedScheduling messages

The event lists every node and why it was filtered out:
`Insufficient cpu/memory`, `node(s) had untolerated taint`,
`node(s) didn't match Pod's node affinity/selector`,
`pod has unbound immediate PersistentVolumeClaims`, and so on. The message
`preemption: 0/3 nodes are available` tells you that evicting lower-priority
Pods would not help either.

## Requests vs limits

Requests drive scheduling and the QoS class. Limits drive runtime enforcement:
CPU throttling and OOM kills. A request of `{{cpu}}` was most likely a units
mistake (cores instead of millicores).

## kubectl 1.37 note

`kubectl describe` shows events by default only for a **single** object.
`kubectl describe pods -l app=x` and prefix matches omit them unless you pass
`--show-events`. When describing several objects, `kubectl events` (optionally
`--for pod/<name>` or `--types=Warning`) is the quicker way to read them.
