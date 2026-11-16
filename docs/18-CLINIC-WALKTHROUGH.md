# Clinic walkthrough: testing the product role by role

This is a script for checking that AarogyaOS works the way a clinic would use it, by playing each member of staff in turn. It follows one invented patient from the front desk to the bill, then repeats parts of the journey to test the rules that keep roles apart.

Use invented names and details only. No real patient information may be entered: the vendor agreements and reviews listed in `17-BASELINE-AND-RELEASE-GATES.md` are not in place.

## Before you start

The API and the app must be running with the demo clinic loaded (`05-INSTALLATION-SETUP.md`). The demo clinic comes with a doctor who has working hours, recording and AI switched on, and consent wording installed.

Sign in each time with organisation `demo-clinic` and password `Demo-pass-2026!`.

| Role | Email |
|---|---|
| Administrator | `admin@demo.example.com` |
| Receptionist | `reception@demo.example.com` |
| Nurse | `nurse@demo.example.com` |
| Doctor | `doctor@demo.example.com` |
| Lab technician | `lab@demo.example.com` |
| Pharmacist | `pharmacist@demo.example.com` |
| Billing clerk | `billing@demo.example.com` |

To change role, use Sign out and sign in again. In a browser you can instead keep one private window per role, which makes the hand-offs quicker. Reloading a browser page signs you out; this is expected.

What the product does not cover, so do not look for it: inpatient care (beds, wards, theatre), a patient-facing app, pharmacy stock, online payment, and sending anything to a patient or insurer. The patient takes part only through the staff in front of them.

Tick each check as you go. Where the result differs from what is written, note the screen, the role and what happened.

## Part 1: the administrator sets up the clinic

Sign in as the administrator.

1. Home shows Billing, Facilities and Administration, and no clinical sections.
2. Open **Facilities**. The demo clinic's site is listed as Active.
3. Open **Administration**, then **Staff and doctors**. All seven demo accounts are listed with their roles. Your own row has no Deactivate button.
4. Add a staff member with an invented name and the Nurse role. They appear in the list.
5. Open **Organisation settings**. Recording and AI processing are on. Under Monthly allowances, enter `600` speech minutes and save. Enter `abc` and confirm the form refuses to save.
6. Open **Usage and audit**. This month's allowances show 0 of 600 speech minutes. Recent activity lists your sign-in and the staff member you added, without any clinical wording.
7. Try to reach a patient: there is no Patients section for this role. An administrator configures the clinic and cannot open a patient record.

## Part 2: a patient walks in

**Receptionist.** Sign in as the receptionist.

1. Home shows Queue, Appointments, Patients, Billing and Follow-ups. There is no Results or Pharmacy.
2. Open **Patients** and search for a name that does not exist. No results.
3. Press **Register new patient**. Enter an invented name, an age, a gender and a ten-digit mobile number, choose a language and register. The patient's page opens with a record number.
4. Register the same name and date of birth again. The app warns that this person may already be registered and offers to open the existing record.
5. On the patient's page, press **Walk-in check-in** and add them to the queue.
6. Open **Queue**. The patient is listed with token 1, Waiting, Not triaged.
7. On the patient's page, press **Consent**. Read out and record agreement for medical care, recording the conversation, turning speech into text and AI processing. Each one is a separate decision and changes from Not given to given.
8. The patient's page shows contact details and a timeline, and no clinical information. This is the rule for reception: they never see the clinical record.

**Nurse.** Sign in as the nurse.

9. Open **Queue** and press **Start triage** for the patient.
10. Enter the main complaint and save it. Enter temperature, pulse, blood pressure and oxygen level and press **Record vitals**. A raised reading, such as a blood pressure of 170 over 105, is flagged as abnormal; an impossible one, such as a pulse of 900, is refused.
11. Under allergies, add one, for example penicillin. The warning that allergy status is not recorded disappears.
12. Press **Done — back to queue**. The patient now shows Triage started.
13. Confirm the nurse has no way to write a diagnosis or a prescription.

## Part 3: the consultation

**Doctor.** Sign in as the doctor.

1. Home shows Results to review and Follow-ups as counts, with Queue, Appointments, Patients and Pharmacy below.
2. Open **Queue** and press **Start consultation**. The consultation opens with the patient's name, age and status across the top, and the allergy and vitals from triage in the side panel.
3. **Notes** tab: choose a layout, fill in two or three headings and save. The note appears under Notes for this visit.
4. **Diagnosis** tab: add a diagnosis, choose Provisional and add it.
5. **Tests** tab: add a lab investigation, for example a complete blood count, and save it as a draft. Then press **Place order**. Until it is placed, nothing reaches the lab.
6. **Prescription** tab: add a medicine with strength, dose, route, frequency and days. Add a second medicine containing the allergy you recorded, for example a penicillin. Press **Review and sign**: the app warns about the allergy and you must acknowledge it before signing. After signing, the prescription shows Signed and can no longer be edited, only voided.
7. **Follow-up** tab: plan a follow-up in one week with a reason and save it.
8. **Documents** tab: draft a visit summary, approve it, and try Print or Share as PDF.
9. Leave the consultation open for Part 4, or go to Part 5 if you are not testing recording.

## Part 4: recording and the draft record

This uses the built-in stand-ins. In a development build the app plays a scripted conversation in place of the microphone, so it tests the flow and not real speech recognition.

1. **Conversation** tab: if consent is missing the app says which, and recording cannot start. With consent in place, switch on **Let software suggest notes** and press **Start AI consultation**.
2. The indicator reads RECORDING and transcript lines appear. Let it run for half a minute, then stop. The indicator must not say RECORDING once you have stopped.
3. **Draft EMR** tab: proposals appear under clinic-note headings, each with the words it came from. Accept one, edit and accept another, and reject a third.
4. Check that only what you accepted appears in the visit. A rejected proposal must not appear anywhere in the record.
5. Sign in as the receptionist, open the patient's Consent page and press **Withdraw consent** for AI processing. Back as the doctor, try to analyse the conversation again: it is refused, and the message says which consent is missing.

## Part 5: finishing the visit

**Doctor.**

1. **Finish** tab: the summary line counts the notes, diagnoses, prescriptions, investigations and follow-ups. If any proposals are undecided, the app lists them first. Press **Complete visit**.
2. Back on **Queue**, the patient is no longer waiting.

**Lab technician.** Sign in as the lab technician.

3. Home shows Patients and Orders and results only.
4. Open **Orders and results**. The blood count you placed is listed. Press **Enter result**, enter the result, its unit and the normal range, and save. A result outside the range you entered is marked abnormal, and one beyond the critical limits is marked critical.

**Doctor.**

5. Home now shows 1 under Results to review. Open it, read the result and press **Mark as reviewed**. The count returns to 0.

**Pharmacist.** Sign in as the pharmacist.

6. Open **Pharmacy**, search for the patient and open the signed prescription. Mark one medicine **Dispensed** and another **Partly**. The record shows who dispensed and when.
7. Confirm a prescription that was never signed does not appear here.

## Part 6: the bill

**Billing clerk.** Sign in as the billing clerk.

1. Open **Billing**. Under To bill, the finished visit is listed. Press **Start invoice**.
2. Add a consultation charge and one other charge, save the charges and check the total. Press **Issue invoice**. It receives a number and can no longer be edited.
3. Press **Record a payment** for part of the amount in cash. The balance falls by that amount. Record the rest by UPI with a reference. The invoice shows as paid.
4. Try to record a payment larger than the balance: it is refused.
5. Issue a credit note for a small amount with a reason, then record a refund of the same amount. Each appears as its own line; nothing earlier is altered.
6. Open **End of day**, enter the cash counted and close the day. It cannot be closed twice.
7. Confirm the billing clerk cannot open the consultation, the notes or the prescription.

## Part 7: a booked appointment and a return visit

**Receptionist.**

1. Open the patient, press **Book appointment**, choose the doctor, tomorrow and a time, and confirm.
2. Open **Appointments** and step forward one day: the booking is listed. Step back to Today.
3. Cancel the appointment and confirm it disappears from the day.
4. Open **Follow-ups**: the follow-up the doctor planned is listed with its due date.

## Part 8: rules that must hold

These checks matter more than the happy path. Each should fail in the way described.

| Try this | Expected |
|---|---|
| As receptionist, open the patient and look for notes, diagnoses or prescriptions | None are shown |
| As billing clerk, look for any clinical section | None exists |
| As nurse, try to prescribe or diagnose | No such option |
| As pharmacist, look for an unsigned prescription | Not visible |
| As lab technician, look for an order still in draft | Not visible |
| As administrator, try to open a patient | No route to a patient |
| As doctor, start recording for a patient with no consent | Refused, with the missing consent named |
| As doctor, edit a signed prescription | Not possible; void and write a new one |
| As billing clerk, edit an issued invoice | Not possible; use a credit note |
| Stop the API while a screen is open, then move to another screen | A banner says there is no connection and that nothing is being saved; it clears when the API returns |
| Enter the wrong password five times | The account locks for a while |

## Part 9: back to the administrator

1. Sign in as the administrator and open **Usage and audit**. The day's actions are listed: registrations, check-in, consent, the consultation, the prescription, dispensing and billing, each with who did it and when.
2. Read several entries and confirm none contains a symptom, a diagnosis, a medicine name or anything the patient said. The audit log records who did what, never what was written.
3. If you ran Part 4, the speech and AI sections show the session and the calls made, with durations and counts only.

## Reporting what you find

For each problem, record the part and step number, the role you were signed in as, what you expected, what happened, and a screenshot. Mark it as one of: blocks the visit, wrong but the visit can continue, or wording and appearance. Anything in Part 8 that does not fail as described is the most serious kind and should be reported first.

This walkthrough covers the journeys the product is built for. It does not replace the device checks in `DEVICE_TEST_PLAN.md`, and passing it does not make the product ready for real patients.
