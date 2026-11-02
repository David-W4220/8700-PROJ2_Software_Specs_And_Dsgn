# Architecture: Space Station Inventory and Resupply

Based on `spec_ayden.md` (revised Nov 2, 2026).

## 1. Overview

The system has two sites. On the station, a single onboard host runs the Station App and its store; every station device is a thin client of that host, so the station has one writer, one clock and one queue. On Earth, the Earth Service is the system of record for item versions, deduplication, conflicts and missions. A sync protocol joins the two: it moves signed station transactions to Earth in recording order, resumes across interrupted link windows, and pulls Earth changes back. The same screens (S1–S7) run on both sides.

## 2. Modules

No station module except the Sync Agent talks to Earth, which keeps NFR-002 ("no crew action depends on a call to the Earth service") true by construction. The organization's identity system is external (Non-goals, User) and is not a module here.

| Module | Responsibility | May depend on |
|---|---|---|
| Screens | Render S1–S7 and send user actions to the local site. Required by the Description's screen list, FR-001–FR-028, FR-002, FR-003 (control hiding) and FR-032 (escape all text when shown). Deployed on station devices and on Earth workstations. | Station: Station Command Handler, Onboard Store (read-only queries through the onboard host), Station Clock, Domain Rules. Earth: Earth Gateway, Domain Rules. |
| Domain Rules | Define the business rules once, as side-effect-free functions used by both sites: field validation, role permissions, the alert rule, the mission state machine, capacity totals and the merge-or-conflict rule. Required because FR-027 makes the station validate before saving while the Earth Service actor and FR-003/FR-032 make Earth enforce every rule; one definition stops the two from disagreeing. | — |
| Station Identity | Authenticate users on board without the Earth link and sign each update with the recorder's key. Required by NFR-003 and User (personal signing key pair). | Onboard Store |
| Station Clock | Be the only source of UTC for station logic, apply Earth's time at each sync, and warn when drift may exceed tolerance. Required by NFR-005 and FR-032 (event-time check). | — |
| Station Command Handler | Validate and commit each crew action as one onboard transaction. Required by FR-006–FR-009, FR-025–FR-027 and NFR-001. | Domain Rules, Station Identity, Station Clock, Onboard Store |
| Onboard Store | Durably persist all station state with serialized, all-or-nothing writes. Required by NFR-001, NFR-002, NFR-006, InventoryUpdate ("never deleted") and the Description ("shared by all station devices"). | — |
| Sync Agent | Send queued station transactions to Earth and apply Earth changes on board. Required by FR-029, FR-030 (station side), FR-025 (receipt as one unit), User (records and keys reach the station on sync) and NFR-004. | Onboard Store, Station Clock, Domain Rules |
| Earth Gateway | Authenticate every caller (Earth users through the identity system, and the station sync channel) and reject actions the caller's role does not allow. Required by FR-003 and NFR-003. | Domain Rules, Earth Store |
| Sync Endpoint | Run the Earth side of a sync session: handshake, signature and revocation check, deduplication, request validation, acknowledgements and the change feed. Required by FR-029, FR-032, NFR-003 and NFR-004. | Inventory Service, Mission Service, Earth Store |
| Inventory Service | Own authoritative item state: apply station and Earth item changes with version checks, merge or flag conflicts, record resolutions, and maintain alerts and item history. Required by FR-009–FR-012, FR-030, FR-031 and SupplyAlert. | Domain Rules, Earth Store |
| Mission Service | Own the mission lifecycle and manifest versions, including receipts and discrepancies arriving from the station. Required by FR-013–FR-026 and the mission state machine. | Domain Rules, Inventory Service, Earth Store |
| Earth Store | Durably persist Earth state with atomic transactions, a synchronous replica and point-in-time backups. Required by NFR-001, NFR-006 and NFR-008. | — |

## 3. Request flow

Scenario: a crew member records usage while the Earth link is down, and the update later synchronizes. This is the path that Goals 1 and 5 depend on; the order follows FR-027 → FR-029 and AC-027 → AC-029, with the checks from FR-030, FR-032 and NFR-003.

**Recording offline (FR-027, AC-027)**

1. The crew member signs in on a station device. Station Identity checks the credential against the user record last synchronized from Earth and unlocks that person's signing key for the session.
2. On S3, the crew member records usage of 2 water packs with a reason. Screens sends the action to the Station Command Handler on the onboard host.
3. The Command Handler opens a write transaction in the Onboard Store. The store serializes it behind any concurrent write from another device.
4. Inside the transaction, the Command Handler reads the current W01 quantity and runs the FR-006 rules from Domain Rules. If any rule fails, the transaction aborts, nothing is written and the error is shown (AC-006).
5. The Station Clock supplies `eventTime`. The store assigns the next commit sequence number, which fixes recording order and the display ID U101. `baseVersion` is the latest Earth version of W01 the station has received (InventoryUpdate).
6. Station Identity signs the update's canonical content (including `updateId`, sequence, `eventTime` and `baseVersion`) with the recorder's key.
7. In the same transaction, the Command Handler writes the new quantity (4), the signed update U101 with status Awaiting sync, and the result of the alert rule (the existing Active alert stays as it is, AC-012).
8. The store commits durably.
9. Only after the commit returns does Screens show "Saved locally", 4 packs and "Awaiting sync". The pending count (FR-001, FR-028) now includes U101.

**Synchronizing when the link returns (FR-029, AC-029)**

10. The Sync Agent's link check, which runs on the NFR-004 interval, reaches the Earth Gateway over an encrypted, mutually authenticated channel using the station credential. No crew member needs to be signed in. Earth records the contact for its link banner (FR-002).
11. Handshake: the station sends its current time and pending count; Earth returns its time and the highest station sequence number it has committed. The Station Clock corrects its offset and checks its drift bound. Earth stores the reported pending count.
12. The Sync Agent selects sendable transactions after Earth's committed sequence, in sequence order, skipping any held behind an open conflict (FR-029, FR-030). It sends U101. Sends are pipelined; acknowledgements return in order.
13. The Sync Endpoint verifies U101's signature against the recorder's public key and checks that the key was not revoked before U101's `eventTime` (NFR-003). Either failure produces the outcome Rejected.
14. The Sync Endpoint looks up `updateId`. An identical resend returns the stored outcome. A resend with different content is Rejected. A new ID continues.
15. The Sync Endpoint applies the FR-032 checks using Earth time and ignores any server-set fields the client sent.
16. In one Earth Store transaction, the Inventory Service runs the FR-030 version check (counting only changes from other sources since `baseVersion`), merges or flags a conflict, applies the change, sets `recordedBy` to the verified signer and `receivedAt` to Earth time, assigns the new `recordVersion`, re-evaluates the alert, and stores the outcome against `updateId`.
17. The transaction commits on the primary and the synchronous replica. Only then does the Sync Endpoint acknowledge U101 with the new item version (or with Conflict or Rejected).
18. In one onboard transaction, the Sync Agent marks U101 Synchronized and stores the new Earth version for W01. The pending count drops. If the acknowledgement was lost, the next handshake (step 11) shows U101 as committed, so it is not resent.
19. Steps 12–18 repeat for the remaining sendable transactions. Transport failures are retried with capped backoff and resume through step 11.
20. With nothing sendable left, the Sync Agent pulls Earth changes made before the pull started: item versions, item data edits, mission changes, user records and keys, and conflict outcomes and resolutions, in Earth commit order.
21. The Sync Agent applies each change in its own onboard transaction: it replaces the item's Earth base, replays the station's still-unacknowledged, non-rejected updates on top (which removes the effect of any Rejected update, FR-029), keeps any conflicted field at its local value marked "Review required", re-evaluates the alert, and advances the pull cursor.
22. When the pull is complete, the sync has fully completed as FR-002 defines it. Both sides record the completion time, and both banners update.

## 4. Design decisions

Your design-decision field again arrived as the placeholder "\<based on the implementation restraints\>", so the key decisions below (K1–K22) are derived from your constraints 1–8 and tagged with the constraint they serve.

### Key decisions

| Decision | Reason |
|---|---|
| **K1 (C1)** One onboard host runs Station Identity, Station Clock, the Command Handler, the Sync Agent and the Onboard Store; devices run only Screens. | NFR-001 requires writes from "all station devices" to be serialized so validation sees the current quantity; one host gives one place to enforce it, plus `quantity` ≥ 0 (InventoryItem) and the FR-006 upper limit. |
| **K2 (C1)** The Onboard Store is an embedded transactional database with durable commit; "Saved locally" is shown only after commit returns. | FR-027, NFR-001 (survives crash, power loss, restart), AC-027. |
| **K3 (C1)** Every crew action is exactly one onboard transaction covering the item, its update record(s), the alert change and, for a receipt, the mission status, `receiptId` and discrepancies. | NFR-001 (all-or-nothing; receipt commits together), FR-025, AC-025, FR-012. |
| **K4 (C1)** Update records are never deleted. The queue is the set of records whose status is Awaiting sync, ordered by sequence; it is a view, not a separate store. | InventoryUpdate ("never deleted"; queued while Awaiting sync), FR-027, NFR-006. |
| **K5 (C1, moved from C8)** Earth acknowledges only after the change commits on the primary and a synchronous replica. Failover uses the replica; point-in-time restore is the fallback. | NFR-008 (never roll back past an acknowledgement; recovery targets), NFR-001. Tracked with the integrity guarantees, as you offered. |
| **K6 (C2)** Recording order is the commit sequence number assigned by the single writer; station display IDs (U…) derive from it. | FR-029 (recording order), InventoryUpdate (U… for station updates), AC-028, AC-027. |
| **K7 (C2)** The station holds a full local copy of everything a crew function reads: items, locations, units, user records and public keys, and all non-final missions with their manifests. | NFR-002 (no crew action depends on Earth), User (records and keys reach the station on sync), FR-025 (receipt "even offline"), FR-001 (next mission), FR-007. |
| **K8 (C2)** The pending list, pending count and recent Rejected list are read from indexes on (status, sequence) and (status, rejection time); S7 is paged. | NFR-002 (S7 and the count stay usable at full queue size), FR-028, FR-001, AC-028. Paging itself is a **preference**. |
| **K9 (C3)** Each person's private key is stored on board encrypted under their sign-in secret and is usable only during their session. Every update is signed at save time. | NFR-003 (recorder's own key; signed when saved; sign-in without the link), User (personal key pair). |
| **K10 (C3)** `recordedBy` is always the verified signer, never the client field or the session that sends the batch. | NFR-003, FR-032 (server-set fields ignored), AC-032 (spoofed author; batch sent by a different person). |
| **K11 (C3)** The sync channel is authenticated with a station credential (mutual authentication) and encrypted. | NFR-003 (traffic encrypted and integrity-protected), FR-029 (automatic sync when nobody may be signed in), AC-032 (batch sent by a different person). |
| **K12 (C4)** Each sync starts with a handshake in which Earth returns the highest station sequence it has committed, and the station resumes after it. | NFR-004 (resume without resending, reordering or skipping). This also detects any Earth-side rollback (NFR-008). |
| **K13 (C4)** The unit of commit and acknowledgement on Earth is one station transaction (a single update, or a whole receipt); batching and pipelining are transport only. | NFR-004 (durable progress; throughput target), NFR-001, FR-025 (receipt synchronized as one unit). Pipelining is a **preference** needed to meet the throughput target over a high-latency link. |
| **K14 (C4)** The link check runs on the NFR-004 interval, independently of retry backoff, and is itself a request to the Earth Gateway, so it also counts as station contact. | NFR-004 (link check interval; backoff only for failed requests), FR-002 (Earth link available after recent contact). |
| **K15 (C5)** The onboard host's Station Clock is the only clock used by station logic. `eventTime` is stamped by the host at commit; device clocks are never read. | NFR-005, FR-032 (future event times rejected), NFR-003 (revocation is judged against event time). |
| **K16 (C5)** The offset is corrected at each handshake before any update is sent. Between syncs the clock keeps a drift bound (time since last correction × measured drift rate) and warns the crew when the bound passes tolerance. | NFR-005 (detect and correct at each sync; warn when drift may exceed tolerance), the Priority note on bulk rejection after long outages. |
| **K17 (C5)** All date logic ("today", Expired, the 7-day windows, display formats) lives in Domain Rules and takes "now" from the site clock in UTC. | NFR-005, FR-004, FR-001, FR-028, the Description's UTC format rule. |
| **K18 (C6)** History content is insert-only, enforced by store permissions: the application has no update or delete rights on history content; only an update's `syncStatus` can change; manifest versions, status-history entries, loading issues, discrepancy notes and resolutions are new rows. | NFR-006, CargoManifest (earlier versions read-only), LoadingIssue (kept on reopen). |
| **K19 (C6)** Earth backups are full-fidelity copies including all history, and every restore is verified against the source before use. | NFR-006 (survive backup and restore unchanged), NFR-008. |
| **K20 (C7)** Alerts are evaluated inside the same write transaction as the triggering change, separately on each site, from that site's item state; `raisedAt` and `resolvedAt` take the triggering change's event time. | SupplyAlert (derived on each side, not synchronized), NFR-007, FR-012. |
| **K21 (C7)** Earth freshness is implemented as defined in FR-002: the Earth Gateway records the last station contact, the Sync Endpoint records the completion time of each full sync and the pending count from the last handshake. | FR-002 (full sync and Earth link definitions), FR-001 ("the count the station last reported"), NFR-007. |
| **K22 (C8)** Planned Earth maintenance is an operating procedure scheduled outside expected link windows; no component is added for it. | NFR-008. |

### Further decisions

| Decision | Reason |
|---|---|
| Station and Earth share one Domain Rules module. | FR-027 (station validates) plus the Earth Service actor and FR-003/FR-032 (Earth enforces every rule). |
| The Inventory Service records the source of every field change, so the FR-030 check can ignore the station's own earlier updates. | FR-030 (only changes from other sources count), AC-030 (successive station changes to the same field). |
| A quantity Correction conflicts with any concurrent quantity change; Usage and Receipt deltas add. | FR-030, AC-030 (correction meets usage). |
| The station shows each item as its last Earth version plus a replay of its unacknowledged, non-rejected updates; conflicted fields keep the local value marked "Review required". | FR-029 (Rejected effect removed at next sync), FR-030, AC-029, AC-030. |
| Later updates on an item with an open conflict are held on board; a receipt is held whole if any of its items is conflicted, and S7 shows "Waiting for conflict review". | FR-029, FR-030, FR-025, FR-028, AC-025 (receipt waits behind a conflict). |
| Earth stores the outcome (acknowledgement, Conflict or Rejected), its time and a content hash for every `updateId` and every `receiptId`. | FR-029, FR-025, AC-029 (identical and altered resend), AC-025 (receipt sent twice), FR-028 (Rejected listed for a period after rejection). |
| Earth-originated updates (corrections, resolutions) take E… display IDs from an Earth Store sequence. | InventoryUpdate (E… for Earth updates), FR-011. |
| History is ordered by event time, ties broken by station commit sequence on the station and by Earth commit order on Earth. | FR-011 (ties by commit order on the side showing the history), AC-011. |
| Every Earth mission, manifest and conflict write re-reads the current status or version in the same transaction and is conditional on it; this includes expected-arrival changes on Approved missions. | FR-016 (stale save; Approved expected arrival), FR-031 (first resolution wins), FR-032 (stale status or version), NFR-001, AC-016, AC-031. |
| Mission IDs come from a sequence in the Earth Store. | FR-014, AC-014. |
| Submission checks collect every failure before rejecting. | FR-017, AC-017. |
| Item search uses an index on name and ID and a unique index on barcode. | NFR-007 (search and barcode lookup target), FR-004, InventoryItem (barcodes unique). The index choice is a **preference**. |

### Where forced decisions are enforced

| Concern | Enforcement point |
|---|---|
| Time | `eventTime`: Station Command Handler, from Station Clock, at commit. Future-time check and revocation-versus-event-time check: Sync Endpoint, using Earth time. `receivedAt`, status-history times, `dispatchedAt`, resolution times, rejection times: Inventory, Mission or Sync Endpoint inside the Earth Store transaction. "Today", Expired, 7-day windows: Domain Rules, with "now" passed in. Clock correction and drift warning: Station Clock, driven by the Sync Agent handshake. Earth link window and last full sync: Earth Gateway and Sync Endpoint. |
| Identity | Offline sign-in and signing: Station Identity, using user records pulled by the Sync Agent. Signature verification, revocation and `recordedBy`: Sync Endpoint. Earth user sign-in, role and `canReopen`: Earth Gateway, via the identity system. Control hiding: Screens, using the Domain Rules permission table (display only; Earth Gateway is authoritative). |
| Concurrency | Station: single writer in the Onboard Store. Earth: conditional writes in Inventory and Mission Services inside Earth Store transactions. Duplicates: unique keys on `updateId` and `receiptId` in the Earth Store, checked by the Sync Endpoint. |
| Errors | Local rule failure: Command Handler aborts; nothing is written. Earth rule, signature or revocation failure: Rejected outcome stored and returned; listed on S7; local effect removed on the next pull. Version clash: Conflict, set by the Inventory Service. Transport failure: Sync Agent retries with capped backoff and resumes through the handshake. Role violation: Earth Gateway returns forbidden. |

## 5. Constraints and known limits

### Your constraints

1. **Durability and transactional integrity.** Met by K1–K5 and K13: one serialized writer on board, durable commit before "Saved locally", one transaction per crew action, records never deleted, and Earth acknowledgement only after a replicated commit. The NFR-008 no-rollback rule is tracked here (K5), and the handshake (K12) would detect a breach. Remaining risk: NFR-001 covers crash, power loss and restart, not loss of the onboard host's storage medium. With no onboard redundancy, that would lose unsynchronized updates.
2. **Offline autonomy and capacity.** Met by K6–K8: every crew function reads and writes only the onboard host, and the queue is an indexed view. Because records are kept for life (K4, NFR-006), onboard storage grows with total history, not queue size; sizing must cover the station's operational life.
3. **Security and offline identity.** Settled by K9–K11 and the revocation check: person-level keys, signing at save time, and a separate station credential for the channel. Earth verifies each update independently of who sends the batch, which is what lets automatic sync and attribution coexist. Limits: anyone who controls the onboard host while a person is signed in can sign as that person, and could stamp an event time before a later revocation; revocations reach the station only at the next sync.
4. **Sync reliability and resumability.** Met by K12–K14 and per-transaction acknowledgement. Throughput depends on pipelining over a high-latency link.
5. **Clock accuracy.** Met by K15–K17. Only one station clock matters, it is corrected before every send, and the crew is warned before drift approaches the FR-032 margin. Limit: the design can only warn; whether NFR-005 holds through a 30-day outage depends on the host's oscillator or an onboard time reference, which the spec does not provide. Clock error also shifts the revocation check (NFR-003).
6. **Audit integrity and retention.** Met by K18–K19. Limit: permissions stop the application from editing history, but not a database administrator with direct access. Detecting that would need hash-chained history, which the spec does not ask for.
7. **Responsiveness.** Met by K20 and K21. Earth freshness is now fully defined by FR-002, so the design only records the three values the banner and dashboard need.
8. **Earth availability and recovery.** Met by K5 and K22. Earth availability affects sync timing only, never crew work (constraint 2).

### What this design does not handle

Earth users cannot see a shortage until the link carries it, and an alert raised and cleared on board between syncs never appears on Earth (accepted in NFR-007). There is no workflow for re-entering a Rejected update beyond recording a new change. There is no onboard failover. The design relies on the external identity system for Earth sign-in, so its availability caps Earth availability (Spec issue 5). Conflict backlogs are unbounded: a long-open conflict holds every later update on that item, and any receipt touching it, indefinitely.

### What would change if requirements grew

- **More than one station.** Every key, sequence, cursor and conflict "source" would need a station ID; the change feed would be per station; and the single-writer assumption would hold per station only.
- **Several locations or batches per item.** The conflict unit (one field of one record) and the alert rule (one quantity against one minimum) would change, and receipts would need to target a location or batch.
- **Notifications outside the app.** A new outbound module would read the Earth Store's change feed; nothing else would change.
- **Forecasting.** A read-only consumer of item history; nothing else would change.
- **User administration in scope.** A new Earth module would own users, roles and keys, replacing the identity-system dependency; its records would reach the station through the existing pull.
- **Onboard redundancy.** The Onboard Store would become a replicated store with agreement between replicas, which removes the simplicity of one writer and one clock.
- **Much higher sync volume.** Earth would need to commit several station transactions per database transaction while still acknowledging each one individually.

## 6. Out of scope

Copied from the spec's Non-goals:

- More than one station.
- More than one inventory record per supply type, or one record at more than one location.
- Consumption forecasting.
- Per-batch tracking.
- Splitting items across locations.
- Notifications outside the app.
- Administering user accounts, roles, the `canReopen` flag and signing keys. These come from the organization's identity system; this system only uses them (see User).

## Spec issues

1. **Held updates after a resolution.** A resolution (FR-031) is an Earth-side change made after the `baseVersion` of any update held behind it. Read literally, FR-030 therefore flags a held station update to the same field as a new conflict, so two station moves of one item, the first in conflict, always produce two conflicts. The spec should say whether held updates are checked against the resolved version instead. The design applies FR-030 as written.
2. **A Rejected receipt.** FR-029 removes a Rejected update's effect on the station, but FR-025 makes a receipt one unit with a mission status change and discrepancies. The spec does not say whether a rejected receipt returns the mission to Shipped on the station and withdraws its discrepancies. The design assumes the whole unit's effect is removed, consistent with FR-029.
3. **Start of the Rejected window.** FR-028 lists Rejected updates "for 7 days after Earth rejects them", but the station learns of a rejection only when the outcome arrives. The design dates the window from Earth's rejection time, carried in the outcome; the spec should confirm.
4. **Expected arrival on an Approved mission.** FR-016 says the change "follows the same rules", but does not say whether it affects recorded loaded quantities or needs re-approval. AC-016 keeps the mission Approved; the design leaves loaded quantities untouched.
5. **Identity system and availability.** Earth sign-in depends on the external identity system (Non-goals, User), but NFR-008 does not say whether its 99.9% target includes that dependency.
