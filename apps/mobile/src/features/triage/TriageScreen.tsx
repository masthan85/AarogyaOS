import { useQuery } from '@tanstack/react-query';
import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';

import {
  addAllergy,
  addMedication,
  addNote,
  recordVitals,
  setTriageCategory,
  startTriage,
  type VitalsInput,
} from '@/api/endpoints';
import type { Observation } from '@/api/schemas';
import { AlertBanner, Button, Card, ChoiceChips, ErrorState, LoadingState, SectionTitle, StatusChip, TextField } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { formatVital, interpretationLabel, interpretationTone, parseNumber, VITAL_LABELS } from '@/domain/clinical';
import { FactRow } from '@/features/consultation/FactRow';
import { useAction } from '@/features/consultation/useAction';
import { useEncounterData } from '@/features/consultation/useEncounterData';

type Fields = Record<'temp' | 'sys' | 'dia' | 'hr' | 'rr' | 'spo2' | 'height' | 'weight' | 'glucose' | 'pain', string>;
const EMPTY: Fields = { temp: '', sys: '', dia: '', hr: '', rr: '', spo2: '', height: '', weight: '', glucose: '', pain: '' };

export function TriageScreen() {
  const { appointmentId, name } = useLocalSearchParams<{ appointmentId: string; name?: string }>();
  // Opening triage is idempotent on the server, so reopening this screen resumes the same visit.
  const started = useQuery({ queryKey: ['triage-start', appointmentId], queryFn: () => startTriage(appointmentId), gcTime: 0, staleTime: Infinity, retry: false });
  if (started.isPending) return <LoadingState label="Opening triage…" />;
  if (started.isError) return <ErrorState message="Could not start triage. Is the patient checked in?" onRetry={() => started.refetch()} />;
  return <TriageForm encounterId={started.data.id} name={name} />;
}

function TriageForm({ encounterId, name }: { encounterId: string; name?: string }) {
  const t = useTheme();
  const data = useEncounterData(encounterId);
  const [complaint, setComplaint] = useState('');
  const [f, setF] = useState<Fields>(EMPTY);
  const [tempUnit, setTempUnit] = useState<'C' | 'F'>('C');
  const [glucoseCtx, setGlucoseCtx] = useState<'RANDOM' | 'FASTING' | 'POST_MEAL'>('RANDOM');
  const [recorded, setRecorded] = useState<Observation[]>([]);
  const [allergy, setAllergy] = useState('');
  const [unsure, setUnsure] = useState(false);
  const [medicine, setMedicine] = useState('');
  const set = (k: keyof Fields) => (v: string) => setF((p) => ({ ...p, [k]: v }));

  const saveComplaint = useAction(
    () => addNote(encounterId, { note_type: 'CHIEF_COMPLAINT', content: complaint, source: 'PATIENT_REPORTED' }),
    () => { setComplaint(''); void data.refresh(); },
  );
  const saveVitals = useAction(
    (body: VitalsInput) => recordVitals(encounterId, body),
    (rows) => { setRecorded((p) => [...rows, ...p]); setF(EMPTY); void data.refresh(); },
  );
  const saveAllergy = useAction(
    (body: Parameters<typeof addAllergy>[1]) => addAllergy(encounterId, body),
    () => { setAllergy(''); setUnsure(false); void data.refresh(); },
  );
  const saveMedicine = useAction(
    () => addMedication(encounterId, { name: medicine }),
    () => { setMedicine(''); void data.refresh(); },
  );
  const category = useAction(
    (c: 'ROUTINE' | 'URGENT' | 'EMERGENCY') => setTriageCategory(encounterId, c),
    () => void data.refresh(),
  );

  const submitVitals = () => {
    const n = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, parseNumber(v)])) as Record<keyof Fields, number | undefined>;
    if (Object.values(n).some((v) => v !== undefined && Number.isNaN(v))) {
      return Alert.alert('Check the numbers', 'Use digits only, for example 98.6 or 120.');
    }
    const body: VitalsInput = {
      ...(n.temp !== undefined ? { temperature: { value: n.temp, unit: tempUnit } } : {}),
      ...(n.sys !== undefined ? { systolic_bp: n.sys } : {}),
      ...(n.dia !== undefined ? { diastolic_bp: n.dia } : {}),
      ...(n.hr !== undefined ? { heart_rate: n.hr } : {}),
      ...(n.rr !== undefined ? { respiratory_rate: n.rr } : {}),
      ...(n.spo2 !== undefined ? { spo2: n.spo2 } : {}),
      ...(n.height !== undefined ? { height_cm: n.height } : {}),
      ...(n.weight !== undefined ? { weight_kg: n.weight } : {}),
      ...(n.glucose !== undefined ? { blood_glucose_mgdl: n.glucose, glucose_context: glucoseCtx } : {}),
      ...(n.pain !== undefined ? { pain_score: n.pain } : {}),
    };
    void saveVitals.run(body);
  };

  if (data.isPending) return <LoadingState />;
  if (data.isError || !data.detail) return <ErrorState message="Could not load this visit." onRetry={() => data.retry()} />;
  const detail = data.detail;
  const closed = detail.encounter.status === 'COMPLETED';

  const num = (label: string, key: keyof Fields, hint?: string) => (
    <View style={{ flexBasis: '47%', flexGrow: 1 }}>
      <TextField label={label} placeholder={hint} keyboardType="decimal-pad" value={f[key]} onChangeText={set(key)} />
    </View>
  );

  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }} keyboardShouldPersistTaps="handled">
      <Card>
        <Text style={{ color: t.text, fontSize: 20, fontWeight: '800' }}>{data.patient?.full_name ?? name ?? 'Patient'}</Text>
        <Text style={{ color: t.textMuted }}>
          {data.patient ? `${data.patient.mrn} · ${data.patient.age_years ?? '?'} yrs · ${data.patient.administrative_gender}` : ''}
        </Text>
        <StatusChip label="Triage" tone="warning" />
      </Card>
      {data.state?.alerts.slice(0, 3).map((a) => <AlertBanner key={a.code + a.message} level={a.level} message={a.message} />)}

      <SectionTitle>Why they came</SectionTitle>
      <Card>
        {detail.notes.filter((n) => n.note_type === 'CHIEF_COMPLAINT').map((n) => (
          <FactRow key={n.id} title={n.content} source={n.source} verification={n.verification_state} />
        ))}
        <TextField label="Main complaint (in the patient’s words)" value={complaint} onChangeText={setComplaint} multiline />
        <Button title="Save complaint" disabled={!complaint.trim() || closed} loading={saveComplaint.pending} onPress={() => void saveComplaint.run()} />
      </Card>

      <SectionTitle>Vital signs</SectionTitle>
      <Card>
        <ChoiceChips label="Temperature unit" value={tempUnit} onChange={setTempUnit} options={[{ value: 'C', label: '°C' }, { value: 'F', label: '°F' }]} />
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.md }}>
          {num(`Temperature (°${tempUnit})`, 'temp')}
          {num('Pulse (bpm)', 'hr')}
          {num('BP systolic', 'sys')}
          {num('BP diastolic', 'dia')}
          {num('Resp. rate (/min)', 'rr')}
          {num('SpO₂ (%)', 'spo2')}
          {num('Height (cm)', 'height')}
          {num('Weight (kg)', 'weight')}
          {num('Glucose (mg/dL)', 'glucose')}
          {num('Pain (0–10)', 'pain')}
        </View>
        {f.glucose ? (
          <ChoiceChips label="Glucose taken" value={glucoseCtx} onChange={setGlucoseCtx} options={[{ value: 'RANDOM', label: 'Random' }, { value: 'FASTING', label: 'Fasting' }, { value: 'POST_MEAL', label: 'After meal' }]} />
        ) : null}
        <Button title="Record vitals" disabled={closed || Object.values(f).every((v) => !v.trim())} loading={saveVitals.pending} onPress={submitVitals} />
        {recorded.map((o) => {
          const label = interpretationLabel(o.interpretation);
          return (
            <View key={o.id} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text style={{ color: t.text }}>{VITAL_LABELS[o.code] ?? o.code}: {formatVital(o)}</Text>
              {label ? <StatusChip label={label} tone={interpretationTone(o.interpretation)} /> : null}
            </View>
          );
        })}
        <Text style={{ color: t.textMuted, fontSize: 12 }}>
          Flags use provisional adult reference ranges that have not yet been clinically signed off. Children are not flagged.
        </Text>
      </Card>

      <SectionTitle>Allergies</SectionTitle>
      <Card>
        {data.state?.allergies.map((a) => (
          <FactRow key={a.id} title={a.is_nka ? 'No known allergies' : a.substance} detail={a.is_nka ? undefined : `${a.severity.toLowerCase()} · ${a.certainty.toLowerCase()}`} source={a.source} verification={a.verification_state} />
        ))}
        {!data.state?.allergy_status_recorded ? <AlertBanner level="WARNING" message="Allergy status not recorded yet. Ask the patient." /> : null}
        <Button title="Patient says: no known allergies" variant="secondary" disabled={closed} loading={saveAllergy.pending} onPress={() => void saveAllergy.run({ is_nka: true, source: 'PATIENT_REPORTED' })} />
        <TextField label="Allergic to" value={allergy} onChangeText={setAllergy} placeholder="Medicine, food or other" />
        <ChoiceChips value={unsure ? 'unsure' : 'sure'} onChange={(v) => setUnsure(v === 'unsure')} options={[{ value: 'sure', label: 'Patient is sure' }, { value: 'unsure', label: 'Not sure / long ago' }]} />
        <Button title="Add allergy" disabled={allergy.trim().length < 2 || closed} loading={saveAllergy.pending}
          onPress={() => void saveAllergy.run({ substance: allergy, certainty: unsure ? 'POSSIBLE' : 'CONFIRMED', source: 'PATIENT_REPORTED' })} />
      </Card>

      <SectionTitle>Medicines they already take</SectionTitle>
      <Card>
        {data.state?.medications.map((m) => (
          <FactRow key={m.id} title={m.name} detail={[m.dose, m.frequency].filter(Boolean).join(' · ') || undefined} source={m.source} verification={m.verification_state} />
        ))}
        <TextField label="Medicine name (as the patient says it)" value={medicine} onChangeText={setMedicine} />
        <Button title="Add medicine" variant="secondary" disabled={medicine.trim().length < 2 || closed} loading={saveMedicine.pending} onPress={() => void saveMedicine.run()} />
      </Card>

      <SectionTitle>Triage category</SectionTitle>
      <Card>
        <ChoiceChips value={(detail.encounter.triage_category ?? undefined) as 'ROUTINE' | 'URGENT' | 'EMERGENCY' | undefined}
          onChange={(c) => void category.run(c)}
          options={[{ value: 'ROUTINE', label: 'Routine' }, { value: 'URGENT', label: 'Urgent' }, { value: 'EMERGENCY', label: 'Emergency' }]} />
        <Text style={{ color: t.textMuted, fontSize: 12 }}>Your clinical judgement. The app never sets this for you.</Text>
      </Card>

      <Button title="Done — back to queue" onPress={() => router.back()} />
    </ScrollView>
  );
}
