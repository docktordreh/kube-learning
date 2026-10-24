Team `{{ns}}` deployed `{{app}}` (3 replicas) into their namespace, but
`kubectl -n {{ns}} get pods` shows nothing.

Make all 3 replicas run **within the namespace's existing policies**. Do not
change, delete or add ResourceQuotas or LimitRanges.
