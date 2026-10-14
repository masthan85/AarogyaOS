const LABELS: Record<string, string> = {
  PATIENT_REGISTERED: 'Registered',
  PATIENT_UPDATED: 'Details updated',
  APPOINTMENT_BOOKED: 'Appointment booked',
  APPOINTMENT_RESCHEDULED: 'Appointment rescheduled',
  APPOINTMENT_CANCELLED: 'Appointment cancelled',
  APPOINTMENT_STATUS_CHANGED: 'Visit status changed',
  PATIENT_CHECKED_IN: 'Checked in',
};

export const eventLabel = (type: string): string =>
  LABELS[type] ?? type.toLowerCase().replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
