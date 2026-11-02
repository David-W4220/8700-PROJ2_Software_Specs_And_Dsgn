# Architecture: Space Station Inventory and Resupply

## 1. Overview

The system has two sites. On the station, a single onboard host runs the Station App and its store; every station device is a thin client of that host, so the station has one writer, one clock and one queue. On Earth, the Earth Service is the system of record for item versions, deduplication, conflicts and missions. A sync protocol joins the two: it moves signed station transactions to Earth in recording order, resumes across interrupted link windows, and pulls Earth changes back. The same screens (S1–S7) run on both sides.

## 2. Modules

No station module except the Sync Agent talks to Earth, which is how NFR-002 ("no crew action depends on a call to the Earth service") is kept true by construction.

| Module | Responsibility | May depend on |
|---|---|---|
| Screens | Render S1–S7 and send user actions to the local site. Required by the Description's screen list, FR-001–FR-028, FR-002, FR-003 (control hiding) and FR-032 (escape all text when shown). Deployed on station devices and on Earth workstations. | Station: Station Command Handler, Onboard Store (read-only queries through the onboard host), Station Clock, Domain Rules. Earth: Earth Gateway, Domain Rules. |
| Domain Rules | Define the business rules once, as side-effect-free functions used by both sites: field validation, role permissions, the alert rule, the mission state machine, capacity totals and the merge-or-conflict rule. Required because FR-027 makes the station validate before saving while the Earth Service actor and FR-003/FR-032 make Earth enforce every rule; one definition stops the two from disagreeing. | — |
| Station Identity | Authenticate users on board without the Earth link and sign each update with the recorder's key. Required by NFR-003. | Onboard Store |
| Station Clock | Be the only source of UTC for station logic, apply Earth's time at each sync, and warn when drift may exceed tolerance. Required by NFR-005 and FR-032 (event-time check). | — |
| Station Command Handler | Validate and commit each crew action as one onboard transaction. Required by FR-006–FR-009, FR-025–FR-027 and NFR-001. | Domain Rules, Station Identity, Station Clock, Onboard Store |
| Onboard Store | Durably persist all station state with serialized, all-or-nothing writes. Required by NFR-001, NFR-002, NFR-006 and the Description ("shared by all station devices"). | — |
| Sync Agent | Send queued station transactions to Earth and apply Earth changes on board. Required by FR-029, FR-030 (station side) and NFR-004. | Onboard Store, Station Clock, Domain Rules |
| Earth Gateway | Authenticate every caller (Earth users and the station sync channel) and reject actions the caller's role does not allow. Required by FR-003 and NFR-003. | Domain Rules, Earth Store |
| Sync Endpoint | Run the Earth side of a sync session: handshake, signature check, deduplication, request validation, acknowledgements and the change feed. Required by FR-029, FR-032, NFR-003 and NFR-004. | Inventory Service, Mission Service, Earth Store |
| Inventory Service | Own authoritative item state: apply station and Earth item changes with version checks, merge or flag conflicts, record resolutions, and maintain alerts and item history. Required by FR-009–FR-012, FR-030 and FR-031. | Domain Rules, Earth Store |
| Mission Service | Own the mission lifecycle and manifest versions, including receipts and discrepancies arriving from the station. Required by FR-013–FR-026 and the mission state machine. | Domain Rules, Inventory Service, Earth Store |
| Earth Store | Durably persist Earth state with atomic transactions, a synchronous replica and point-in-time backups. Required by NFR-001, NFR-006 and NFR-008. | — |

## 3. Request flow

Scenario: a crew member records usage while the Earth link is down, and the update later synchronizes. This is the path that Goals 1 and 5 depend on; the order follows FR-027 → FR-029 and AC-027 → AC-029, with the checks from FR-030 and FR-032.

**Recording offline (FR-027, AC-027)**

1. The crew member signs in on a station device. Station Identity checks the credential against the onboard user record and unlocks that person's signing key for the session.
2. On S3, the crew member records usage of 2 water packs with a reason. Screens sends the action to the Station Command Handler on the onboard host.
3. The Command Handler opens a write transaction in the Onboard Store. The store serializes it behind any concurrent write from another device.
4. Inside the transaction, the Command Handler reads the current W01 quantity and runs the FR-006 rules from Domain Rules. If any rule fails, the transaction aborts, nothing is written and the error is shown (AC-006).
5. The Station Clock supplies `eventTime`. The store assigns the next commit sequence number, which fixes recording order and the display ID U101. `baseVersion` is the last Earth version of W01 the station holds.
6. Station Identity signs the update's canonical content (including `updateId`, sequence, `eventTime` and `baseVersion`) with the recorder's key.
7. In the same transaction, the Command Handler writes the new quantity (4), the signed update U101 with status Awaiting sync, and the result of the alert rule (the existing Active alert stays as it is, AC-012).
8. The store commits durably.
9. Only after the commit returns does Screens show "Saved locally", 4 packs and "Awaiting sync". The pending count (FR-001, FR-028) now includes U101.

**Synchronizing when the link returns (FR-029, AC-029)**

10. The Sync Agent's link probe detects the link (NFR-004 start target) and opens an encrypted, mutually authenticated session with the Earth Gateway using the station credential. No crew member needs to be signed in.
11. Handshake: the station sends its current time and pending count; Earth returns its time and the highest station sequence number it has committed. The Station Clock corrects its offset and checks its drift bound. Earth records "Station link available" and the reported pending count.
12. The Sync Agent selects sendable transactions after Earth's committed sequence, in sequence order, skipping any held behind an open conflict (FR-030). It sends U101. Sends are pipelined; acknowledgements return in order.
13. The Sync Endpoint verifies U101's signature against the recorder's enrolled public key. A bad signature produces the outcome Rejected.
14. The Sync Endpoint looks up `updateId`. An identical resend returns the stored outcome. A resend with different content is Rejected. A new ID continues.
15. The Sync Endpoint applies the FR-032 checks using Earth time and ignores any server-set fields the client sent.
16. In one Earth Store transaction, the Inventory Service runs the version check and the FR-030 merge-or-conflict rule, applies the change, sets `recordedBy` to the verified signer and `receivedAt` to Earth time, assigns the new `recordVersion`, re-evaluates the alert, and stores the outcome against `updateId`.
17. The transaction commits on the primary and the synchronous replica. Only then does the Sync Endpoint acknowledge U101 with the new item version (or with Conflict or Rejected).
18. In one onboard transaction, the Sync Agent marks U101 Synchronized and stores the new Earth version for W01. The pending count drops. If the acknowledgement was lost, the next handshake (step 11) shows U101 as committed, so it is not resent.
19. Steps 12–18 repeat for the remaining sendable transactions. Transport failures are retried with capped backoff and resume through step 11.
20. With nothing sendable left, the Sync Agent pulls Earth changes since its pull cursor: item versions, item data edits, mission changes, and conflict outcomes and resolutions, in Earth commit order.
21. The Sync Agent applies each change in its own onboard transaction: it replaces the item's Earth base, replays the station's still-unacknowledged updates on top, keeps any conflicted field at its local value marked "Review required", re-evaluates the alert, and advances the pull cursor.
22. When the pull reaches Earth's head, both sides record the completion time of a full sync, and both banners (FR-002) update.

## 4. Design decisions

Your design-decision field arrived as the placeholder "\<based on the implementation restraints\>", so the key decisions below (K1–K22) are derived from your constraints 1–8 and tagged with the constraint they serve.

### Key decisions

| Decision | Reason |
|---|---|
| **K1 (C1)** One onboard host runs Station Identity, Station Clock, the Command Handler, the Sync Agent and the Onboard Store; devices run only Screens. | NFR-001 requires writes from "all station devices" to be serialized so validation sees the current quantity; one host gives one place to enforce it, plus `quantity` ≥ 0 (InventoryItem) and the FR-006 upper limit. |
| **K2 (C1)** The Onboard Store is an embedded transactional database with durable commit; "Saved locally" is shown only after commit returns. | FR-027 ("saved … before it is shown as saved"), NFR-001 (survives crash, power loss, restart), AC-027. |
| **K3 (C1)** Every crew action is exactly one onboard transaction covering the item, its update record(s), the alert change and, for a receipt, the mission status and discrepancies. | NFR-001 (all-or-nothing; receipt commits together), FR-025, AC-025, FR-012. |
| **K4 (C1)** Update records are never deleted. The "queue" is the set of records whose status is Awaiting sync, ordered by sequence. | FR-027 (never deleted before acknowledgement), FR-011 (history shows sync status, so records outlive acknowledgement), NFR-006. See Spec issue 2. |
| **K5 (C1, moved from C8)** Earth acknowledges only after the change commits on the primary and a synchronous replica. Failover uses the replica; point-in-time restore is the fallback. | NFR-008 (never roll back past an acknowledgement; recovery targets), NFR-001. Tracked with the integrity guarantees, as you offered. |
| **K6 (C2)** Recording order is the commit sequence number assigned by the single writer; the station's display IDs derive from it. | FR-029 (recording order), AC-028 (U101 before U102), AC-027 (U101). |
| **K7 (C2)** The station holds a full local copy of everything a crew function reads: items, locations, units, user records and public keys, and all non-final missions with their manifests. | NFR-002 (no crew action depends on Earth), FR-025 (receipt "even offline"), FR-001 (next mission), FR-007 (existing locations). |
| **K8 (C2)** The pending list and pending count are read from an index on (status, sequence); S7 is paged. | NFR-002 (S7 and the count stay usable at full queue size), FR-028, FR-001. Paging itself is a **preference**. |
| **K9 (C3)** Each person has a signing key pair enrolled by Earth. The private key is stored on board encrypted under the person's sign-in secret and is usable only during their session. Every update is signed at save time. | NFR-003 ("verifiable proof of the person", "signed … when it is saved", authenticate "without the Earth link"). A device-only credential would attribute to a device, not a person (Goal 4). See Spec issue 3. |
| **K10 (C3)** `recordedBy` is always the verified signer. It is never taken from the client field or from the session that sends the batch. | NFR-003, FR-032 (server-set fields ignored), AC-032. See Spec issue 4. |
| **K11 (C3)** The sync session is authenticated with a station credential (mutual authentication) and encrypted. | NFR-003 (traffic encrypted and integrity-protected), FR-029 (automatic sync when nobody may be signed in). |
| **K12 (C4)** Each sync starts with a handshake in which Earth returns the highest station sequence it has committed, and the station resumes after it. | NFR-004 (resume without resending, reordering or skipping). This also detects any Earth-side rollback (NFR-008). |
| **K13 (C4)** The unit of commit and acknowledgement on Earth is one station transaction; batching and pipelining are transport only. | NFR-004 (durable progress in short windows; 1,000 updates per window), NFR-001 (receipt atomic on Earth too). |
| **K14 (C4)** The link probe runs on a fixed interval within the NFR-004 start target, independent of request retry backoff, which is capped per NFR-004. | NFR-004 (start target and backoff cap). See Spec issue 6. |
| **K15 (C5)** The onboard host's Station Clock is the only clock used by station logic. `eventTime` is stamped by the host at commit; device clocks are never read. | NFR-005, FR-032 (future event times rejected). One disciplined clock replaces many. |
| **K16 (C5)** The offset is corrected at each handshake before any update is sent. Between syncs the clock keeps a drift bound (time since last correction × measured drift rate) and warns the crew when the bound passes tolerance. | NFR-005 (detect and correct at each sync; warn when drift may exceed tolerance), Priority note on bulk rejection after long outages. |
| **K17 (C5)** All date logic ("today", Expired, past 7 days, display formats) lives in Domain Rules and takes "now" from the site clock in UTC. | NFR-005, FR-004, FR-001, the Description's UTC format rule. |
| **K18 (C6)** History content is insert-only, enforced by store permissions: the application has no update or delete rights on history content; only `syncStatus` on an update can change; manifest versions, status-history entries, discrepancy notes and resolutions are new rows. | NFR-006, CargoManifest (earlier versions read-only). |
| **K19 (C6)** Earth backups are full-fidelity copies including all history, and every restore is verified against the source before use. | NFR-006 (survive backup and restore unchanged), NFR-008. |
| **K20 (C7)** Alerts are evaluated inside the same write transaction as the triggering change, on whichever site commits it. | NFR-007 (station alert within its target; Earth alert within its target of the sync), FR-012. |
| **K21 (C7)** Earth-side freshness is defined as: "Station link" available while a session is open or a handshake succeeded within the probe interval; "Last sync" is the Earth time at which the last full sync (step 22) completed; the pending count is the value from the last handshake. | FR-002, FR-001 ("the count the station last reported"), NFR-007 (banner shows how current Earth data is). See Spec issue 12. |
| **K22 (C8)** Planned Earth maintenance is an operating procedure scheduled outside expected link windows; no component is added for it. | NFR-008. |

### Further decisions

| Decision | Reason |
|---|---|
| Station and Earth share one Domain Rules module. | FR-027 (station validates) plus the Earth Service actor and FR-003/FR-032 (Earth enforces every rule). |
| Conflict detection is per field: an update conflicts only if a field it touches changed after its `baseVersion` from a source other than this station's own earlier updates, or if the result would be negative. | FR-030, AC-030. The "other source" part is needed so two offline moves of the same item do not conflict with each other. See Spec issue 7. |
| Usage and Receipt deltas are added together. A Correction sets an absolute value, so a concurrent quantity change on the other side is a same-field conflict. | First half: FR-030. Second half: **preference**, since the spec is silent (Spec issue 18). |
| The station shows each item as its last Earth version plus a replay of the station's unacknowledged updates; conflicted fields keep the local value marked "Review required". | FR-030, AC-030 ("the station still shows Store B"). |
| Later updates on an item with an open conflict are held on board. A transaction touching several items (a receipt) is held whole if any of them is conflicted. | FR-030 (later updates wait), NFR-001 (receipt all-or-nothing). See Spec issue 10. |
| Earth stores the outcome (acknowledgement, Conflict or Rejected) and a content hash for every `updateId`, and for every receipt submission ID. | FR-029, AC-029 (identical and altered resend), AC-025 (receipt sent twice). See Spec issue 9. |
| Every Earth mission, manifest and conflict write re-reads the current status or version in the same transaction and is conditional on it. | FR-016 (stale save), FR-031 (first resolution wins), FR-032 (stale status or version), NFR-001, AC-016, AC-031. |
| Mission IDs come from a sequence in the Earth Store. | FR-014, AC-014. |
| Submission checks collect every failure before rejecting. | FR-017, AC-017. |
| Item search uses an index on name and ID and a unique index on barcode. | NFR-007 (search and barcode lookup target), FR-004, InventoryItem (barcodes unique). The index choice is a **preference**. |
| Earth derives its own alerts from Earth item state rather than copying station alert records; Earth `raisedAt` is the `eventTime` of the triggering update. | **Preference**; the spec does not say whether alerts are synchronized (Spec issue 13). |

### Where forced decisions are enforced

| Concern | Enforcement point |
|---|---|
| Time | `eventTime`: Station Command Handler, from Station Clock, at commit. Future-time check: Sync Endpoint, using Earth time. `receivedAt`, status-history times, `dispatchedAt`, conflict resolution time: Inventory or Mission Service inside the Earth Store transaction. "Today", Expired, 7-day window: Domain Rules, with "now" passed in. Clock correction and drift warning: Station Clock, driven by the Sync Agent handshake. |
| Identity | Offline sign-in and signing: Station Identity. Signature verification and `recordedBy`: Sync Endpoint. Earth user sign-in, role and `canReopen`: Earth Gateway. Control hiding: Screens, using the Domain Rules permission table (display only; Earth Gateway is authoritative). |
| Concurrency | Station: single writer in the Onboard Store. Earth: conditional writes in Inventory and Mission Services inside Earth Store transactions. Duplicates: unique key on `updateId` and receipt submission ID in the Earth Store, checked by the Sync Endpoint. |
| Errors | Local rule failure: Command Handler aborts; nothing is written. Earth rule failure: Rejected outcome stored and returned; shown on S7. Version clash: Conflict, set by the Inventory Service. Transport failure: Sync Agent retries with capped backoff and resumes through the handshake. Role violation: Earth Gateway returns forbidden. |

## 5. Constraints and known limits

### Your constraints

1. **Durability and transactional integrity.** Met by K1–K5 and K13: one serialized writer on board, durable commit before "Saved locally", one transaction per crew action, records never deleted, and Earth acknowledgement only after a replicated commit. The NFR-008 rule against rolling back past an acknowledgement is tracked here (K5), and the handshake (K12) would detect a breach. Remaining risk: NFR-001 covers crash, power loss and restart, not loss of the onboard host's storage medium. This design has no onboard redundancy, so such a loss would lose unsynchronized updates.
2. **Offline autonomy and capacity.** Met by K6–K8: every crew function reads and writes only the onboard host, and the queue is an indexed view, not a separate store. Because records are kept for life (K4, NFR-006), onboard storage grows with total history, not with queue size; sizing must cover the station's operational life.
3. **Security and offline identity.** Settled by K9–K11: person-level keys, signing at save time, and a station credential for the channel. The protocol depends on this, because Earth verifies each update's signature independently of who sends the batch. Limits: anyone who controls the onboard host while a person is signed in can sign as that person; revoking a person's key reaches the station only at the next sync.
4. **Sync reliability and resumability.** Met by K12–K14 and the per-transaction acknowledgement. Throughput depends on pipelining, because per-transaction round trips over a high-latency link would otherwise miss the NFR-004 rate.
5. **Clock accuracy.** Met by K15–K17. Only one station clock matters, it is corrected before every send, and the crew is warned before drift can approach the FR-032 margin. Limit: this design can only warn; whether NFR-005 is achievable over a 30-day outage depends on the host's oscillator or an onboard time reference, which the spec does not provide.
6. **Audit integrity and retention.** Met by K18–K19. Limit: permissions stop the application from editing history, but not a database administrator with direct access. Detecting that would need hash-chained history, which the spec does not ask for.
7. **Responsiveness.** Met by K20 (alerts inside the write) and K21 (Earth freshness defined as last full sync time plus reported pending count).
8. **Earth availability and recovery.** Met by K5 and K22. Earth availability does not affect crew work (constraint 2), only sync timing.

### What this design does not handle

The design cannot make a shortage visible on Earth before the link carries it; for Earth users, Goal 2 is bounded by link availability, and an alert raised and cleared on board between syncs never appears on Earth (Spec issue 13). It has no workflow for re-entering a Rejected update; the station's displayed value silently converges to Earth's on the next pull (Spec issue 8). It has no onboard failover. It does not manage user enrollment, role changes or key revocation, because the spec has no requirement for them (Spec issue 17). It does not bound conflict backlogs; a long-open conflict holds every later update on that item indefinitely.

### What would change if requirements grew

- **More than one station.** Every key, sequence, cursor and conflict "source" would need a station ID; the change feed would be per station; and conflict detection would need to tell stations apart. The single-writer assumption would hold per station only.
- **Several locations or batches per item.** The conflict unit (one field of one record) and the alert rule (one quantity against one minimum) would change, and receipts would need to target a location or batch.
- **Notifications outside the app.** A new outbound module would read the Earth Store's change feed; nothing else would change.
- **Forecasting.** A read-only consumer of item history; nothing else would change.
- **Onboard redundancy.** The Onboard Store would become a replicated store with agreement between replicas, which removes the simplicity of one writer and one clock.
- **Much higher sync volume.** Earth would need to commit several station transactions per database transaction while still acknowledging each one individually.

## 6. Out of scope

The spec has no Non-goals section (Spec issue 1). This is copied from its Description:

> The system covers one station with one inventory record per supply type at one location; consumption forecasting, per-batch tracking, splitting items across locations and notifications outside the app are out of scope.

## Spec issues

1. **No Non-goals section.** Section 6 uses the Description's out-of-scope sentence instead.
2. **Deleting acknowledged updates.** NFR-008's trace says the station deletes an update once Earth acknowledges it, but FR-011 shows sync status in station history and NFR-006 requires retention. The design keeps every record (K4); the NFR-008 trace should be corrected.
3. **"User's or device's credential."** NFR-003 allows a device credential, but a device credential cannot give "verifiable proof of the person". The design uses person-level keys (K9).
4. **Who `recordedBy` is.** AC-032 says "the signed-in user", while NFR-003 says the recorder, not the session that sends the batch. The design uses the verified signer (K10); AC-032 should be reworded.
5. **Recording order versus held updates.** FR-029 sends in recording order, but FR-030 holds later updates on a conflicted item. Global order cannot hold while conflicts are open. The design keeps order within each item and across everything not held.
6. **Backoff cap versus start time.** NFR-004's backoff cap is longer than its start target, so a capped retry could miss the start target. The design separates the link probe from retry backoff (K14).
7. **`baseVersion` for consecutive offline updates.** Read literally, FR-030 would flag a second offline move of the same item as a conflict with the station's own first move. The design ignores the station's own earlier updates when checking for conflicts.
8. **Local effect of a Rejected update.** The spec does not say whether the station keeps or reverts a change that Earth rejects. The design lets the next pull replace it with Earth's value; the crew should probably be told explicitly.
9. **Receipt as a sync unit.** FR-025 creates Receipt updates only for lines above 0, but the mission status and discrepancies (and an all-zero receipt) are not InventoryUpdates, so the model gives them no queue entry or deduplication ID, yet AC-025 requires "the same receipt" to be recognized. The design adds a receipt submission ID to the receipt transaction.
10. **Receipt touching a conflicted item.** FR-030 holds updates on a conflicted item, and NFR-001 requires the receipt to be atomic, so the whole receipt waits and Earth sees the mission as Shipped until the conflict is resolved.
11. **Display IDs for Earth-originated updates.** Earth corrections and resolutions also appear in history (FR-011), but nothing says how their display IDs avoid colliding with the station's U-numbers.
12. **"Fully completed" sync.** FR-002 does not define it when updates are held behind a conflict. The design treats a sync as complete when nothing sendable remains and the pull has reached Earth's head (step 22).
13. **Alerts across sites.** NFR-007 speaks of "a station alert" appearing on Earth, but SupplyAlert has no sync status and FR-029 synchronizes only updates. The design derives Earth alerts from Earth state.
14. **Setting expected arrival.** Dispatch requires an expected arrival, but FR-016 implies it is edited only in Draft. It is unclear whether it can be set or changed while Approved.
15. **"Loading data cleared" on reopen.** FR-020 does not say whether loading issues are cleared along with loaded quantities.
16. **Rejected updates on S7.** FR-028 lists Awaiting sync and Conflict only, but AC-029 shows Rejected on the Sync screen.
17. **User and key management.** Offline sign-in, roles, `canReopen` and signing keys must be provisioned to the station, but no requirement covers enrollment, role changes or revocation.
18. **Correction versus concurrent usage.** FR-030 makes usage and receipt additive but is silent about an absolute Correction meeting a concurrent delta. The design treats it as a conflict.
19. **History ordering.** FR-011 orders by event time, but event times come from two clocks and may tie. The design breaks ties by commit order, which the spec does not state.
20. **"Recent activity" events.** FR-001 does not define which records count as events (updates only, or mission status changes and alerts too).
