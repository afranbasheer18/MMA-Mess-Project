# MongoDB Collection Audit

Audit scope: the Flask backend in `app.py`, frontend files under `static/` and
`templates/`, and the 19 collection names supplied for database
`mma_hostel_mess`.

**Database access was not configured during this audit.** Collection existence,
document counts, sample contents, backups, and cross-collection data
dependencies could not be verified. Classifications below are based on source
references, not live Atlas contents. “TEST/UNUSED” means no reference was found
in the inspected application files; it does not prove that the collection is
empty or unused by external consumers. No collection was modified.

Classification:

- **ESSENTIAL** — active core workflow or data integrity dependency.
- **HISTORICAL** — archive or apparent legacy/history data that must be retained.
- **OPTIONAL** — active ancillary feature, or an unverified collection with no
  current source reference.
- **TEST/UNUSED** — no source reference found; test/unused status is unverified.

| Collection | Inventory | Class | API routes / code evidence | Frontend feature | Count |
|---|---|---|---|---|---|
| `admin_presence` | Supplied | OPTIONAL | `/api/users/admin-presence` | Admin active-user presence indicator | Not inspected |
| `bill_archive` | Supplied | HISTORICAL | `/api/bills/archive` GET/POST; archive helpers (`app.py` around 4191–4243) | Archived bills/history | Not inspected |
| `bills` | Supplied | ESSENTIAL | `/api/bills` (generation, updates, payment, snapshots); bill helpers and routes (`app.py` around 969–1005, 3488–4089) | Student bills and admin billing | Not inspected |
| `connection_test` | Supplied | TEST/UNUSED | No reference found in `app.py`, `static/`, or `templates/` | None identified | Not inspected |
| `feedback` | Supplied | OPTIONAL | `/api/feedback` GET/POST | Student feedback and admin feedback view | Not inspected |
| `general_settings` | Supplied | ESSENTIAL | `/api/settings` GET/POST and `/api/settings/food-points` PATCH; settings helpers (`app.py` around 827–1102) | Application settings and meal configuration | Not inspected |
| `meal_cancellation_adjustments` | Supplied | ESSENTIAL | Billing cancellation-adjustment processing (`app.py` around 3712–3713) | Billing adjustment accounting | Not inspected |
| `meal_cancellations` | Supplied | ESSENTIAL | `/api/meal-records/cancellations`; helpers, summaries, and routes (`app.py` around 1172–1190, 3566–3683, 5910+) | Meal cancellation actions and summaries | Not inspected |
| `meal_records` | Supplied | ESSENTIAL | `/api/meal-records` and `/api/meal-records/my-today`; permissions and no-food routes | Student/admin meal records and permissions | Not inspected |
| `mess_bill_monthly_ledger` | Supplied | HISTORICAL | No reference found in inspected application files; name suggests historical billing data | None identified | Not inspected |
| `mess_bill_payment_months` | Supplied | HISTORICAL | No reference found in inspected application files; name suggests payment-period history | None identified | Not inspected |
| `mess_entries` | Supplied | ESSENTIAL | `/api/entries` (today, tomorrow, history, create/update/delete); helpers (`app.py` around 876–922, 2872–3190, 4339+) | Admin Today/Tomorrow entries and meal selections | Not inspected |
| `no_food_requests` | Supplied | ESSENTIAL | `/api/meal-records/no-food-requests` and approval/rejection actions | Student no-food requests and admin approvals | Not inspected |
| `notifications` | Supplied | OPTIONAL | `/api/notifications` and read/clear actions | Student/admin notifications | Not inspected |
| `password_reset_rate_limits` | Supplied | TEST/UNUSED | No reference found in `app.py`, `static/`, or `templates/` | No feature identified; external/auth integration unknown | Not inspected |
| `registration_requests` | Supplied | ESSENTIAL | `/api/users/registrations` and approve/reject actions | Student registration and admin approval workflow | Not inspected |
| `today_menu` | Supplied | ESSENTIAL | `/api/menu/today` and `/api/menu/tomorrow`; menu helpers (`app.py` around 738–750) | Today/tomorrow menu for admin and student pages | Not inspected |
| `users` | Supplied | ESSENTIAL | `/api/auth/*`, `/api/users/*`; user helpers, auth, and user routes (`app.py` around 515–651, 1808+, 2538+) | Authentication, identities, roles, and user administration | Not inspected |
| `weekly_menu` | Supplied | ESSENTIAL | `/api/menu/weekly` GET/PUT; menu helpers (`app.py` around 757–795) | Weekly meal schedule | Not inspected |
| `bill_drafts` | Application-only | OPTIONAL | `/api/bills/drafts` GET/PUT; draft helpers and bill generation cleanup (`app.py` around 3840–4064) | Admin editable monthly bill drafts | Not inspected |
| `charge_configs` | Application-only | OPTIONAL | `/api/bills/charge-configs` GET/POST (`app.py` around 4137–4162) | Admin monthly fixed/water/reserved-fund charges | Not inspected |
| `expenses` | Application-only | ESSENTIAL | `/api/bills/expenses` GET/POST and monthly billing calculation (`app.py` around 1605, 4105–4127) | Admin expenses and point-rate/bill calculations | Not inspected |
| `user_adjustments` | Application-only | ESSENTIAL | `/api/bills/user-adjustments` (`app.py` around 4182) | Admin student-specific monthly fines and discounts | Not inspected |

## Findings and safe next steps

- The supplied inventory contains 19 names. The application also references
  four collections not on that list: `bill_drafts`, `charge_configs`, `expenses`,
  and `user_adjustments`. Confirm the live Atlas inventory before relying on
  either list as complete.
- The application has no identified collection-drop operation or scheduled
  cleanup that removes these collections. The draft cleanup referenced above
  applies to bill-draft records during billing, not collection deletion.
- **Proposed deletion list: none.** Collections classified TEST/UNUSED remain
  unverified and are not deletion recommendations. Before any future deletion,
  verify live counts and contents, external consumers, and a tested backup, and
  obtain explicit approval.
- To complete the data portion, provide a read-only Atlas connection or an
  authorized collection inventory with per-collection counts and backup
  confirmation. Do not run `drop`, `deleteMany`, or database-wide cleanup as
  part of this source-only audit.
