# MMA Hostel Mount Road — Client Requirement Update

The original project files and existing purple/dark UI were preserved. The update adds:

1. User password change in Settings.
2. Tomorrow mess entry uses Breakfast/Lunch/Dinner quantities from 0–2, with the Admin-configured cutoff enforced dynamically.
3. Planned-vs-confirmed meal records and mismatch/additional-entry visibility through the existing Meal Records screen.
4. User requests for complaints, improvement suggestions, hostel leave, meal permission and meal cancellation.
5. Breakfast/lunch/dinner rates remain in the existing bill calculator and are displayed in generated bills.
6. Admin/Mess Secretary request workflow UI (approval/rejection).
7. Cancellation requests can zero the affected meal entry after approval.
8. Admin Meal Records cross-check planned quantities against today's saved quantities and shows mismatch states.
9. Admin request to cancel a meal for an individual; global meal cancellation controls can be added to the same workflow.
10. Feedback remains available per meal and general complaint/suggestion requests are added.
11. Configurable food limits: Puri 4, Dosa 4, Idly 4, Chicken piece 1, Egg 1, Fish Fry 1, Banana 1, Poriyal 1.
12. Admin User Access screen shows status, last login, last activity and last mess entry where recorded.
13. Invitation generation and pending registration approval flow with automatic STU/WRK user ID generation.
14. Mobile refinements for small phones and admin tables.

## Important data mode note

This ZIP keeps the original browser/localStorage data model so the current project remains runnable immediately without destroying existing data. Browser localStorage is **not a shared database across different phones**.

For real multi-device access (student phone -> shared admin dashboard), connect the existing data layer to Supabase/PostgreSQL and Supabase Auth. Do not store production passwords as plaintext. The UI/workflow additions are already separated into `client-updates.js` and `admin-updates.js` so the backend can be connected without replacing the existing UI.
