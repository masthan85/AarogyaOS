import type { EncounterDetail } from '@/api/schemas';

import { visitText } from '../handoff';

const fact = { id: 'x', source: 'DOCTOR_ENTERED', verification_state: 'CONFIRMED', is_current: true };
const detail = {
  encounter: { id: 'e', patient_id: 'p', appointment_id: 'a', facility_id: 'f', practitioner_id: 'd', status: 'IN_PROGRESS', triage_category: null },
  notes: [
    { ...fact, note_type: 'PLAN', content: 'Rest and fluids' },
    { ...fact, note_type: 'HPI', content: 'Fever for 3 days', verification_state: 'AI_GENERATED' },
  ],
  vitals: [{ ...fact, code: 'TEMPERATURE', value: 38.4, unit: 'C', original_value: null, original_unit: null, interpretation: 'HIGH', observed_at: 'x' }],
  conditions: [{ ...fact, display: 'Viral fever', certainty: 'PROVISIONAL', clinical_status: 'ACTIVE', category: 'x' }],
  prescriptions: [
    { id: 'r1', status: 'SIGNED', items: [{ id: 'i', position: 1, medicine_name: 'Paracetamol', strength: '500 mg', dose: '1 tablet', route: 'ORAL', frequency: 'twice daily', duration_days: 3, instructions: null }] },
    { id: 'r2', status: 'DRAFT', items: [{ id: 'j', position: 1, medicine_name: 'Secret draft', strength: null, dose: '1', route: 'ORAL', frequency: 'od', duration_days: null, instructions: null }] },
  ],
  orders: [
    { id: 'o1', category: 'LAB', name: 'CBC', priority: 'ROUTINE', status: 'ORDERED' },
    { id: 'o2', category: 'LAB', name: 'Cancelled test', priority: 'ROUTINE', status: 'CANCELLED' },
  ],
  follow_ups: [{ id: 'f1', due_date: '2026-03-10', reason: 'Review', status: 'PENDING' }],
} as unknown as EncounterDetail;

describe('visitText', () => {
  const text = visitText(detail, 'Lakshmi Devi · P0000001 · 45 yrs');
  it('puts the record in a fixed order and marks what nobody has verified', () => {
    expect(text.split('\n')[0]).toBe('Lakshmi Devi · P0000001 · 45 yrs');
    expect(text.indexOf('History of present illness')).toBeLessThan(text.indexOf('Plan: Rest'));
    expect(text).toContain('History of present illness: Fever for 3 days [unverified]');
    expect(text).toContain('Plan: Rest and fluids\n');
    expect(text).toContain('- Temperature: 38.4 C');
    expect(text).toContain('- Viral fever (provisional)');
  });
  it('includes only signed prescriptions and live orders', () => {
    expect(text).toContain('- Paracetamol 500 mg: 1 tablet, oral, twice daily for 3 days');
    expect(text).not.toContain('Secret draft');
    expect(text).toContain('- CBC (lab, routine)');
    expect(text).not.toContain('Cancelled test');
    expect(text).toContain('- 2026-03-10: Review');
  });
  it('says nothing about sections that are empty', () => {
    const bare = visitText({ ...detail, notes: [], vitals: [], conditions: [], prescriptions: [], orders: [], follow_ups: [] } as EncounterDetail, 'X');
    expect(bare).toBe('X');
  });
});
