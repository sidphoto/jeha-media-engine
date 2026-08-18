# M5.4 Release Configuration Boundary

M5.4 is planning-only. It consumes a private M5.3 upload record and matching M5.2 metadata package, validates lineage, and freezes optional thumbnail, future schedule, and target visibility intent.

It performs **no YouTube mutation**.

## Safety rules

- remote video must still be `private`
- metadata must still declare `privacyStatus=private`
- any `publishAt` must be strictly in the future
- a scheduled release is only a plan for a future `public` target
- thumbnail must be a local JPEG/PNG, non-empty, <= 2 MiB, with SHA-256 recorded
- thumbnail upload, `videos.update`, scheduling, and visibility changes remain disabled
- non-private intent requires a separate M5.5 approval bound to the exact `configuration_hash`

Final status: `RELEASE_CONFIGURATION_READY`.
