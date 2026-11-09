import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Alert, Text, View } from 'react-native';

import {
  addImmunisation,
  addProcedure,
  addReferral,
  getHistory,
  updateReferral,
  verifyFact,
} from '@/api/endpoints';
import { useAuth } from '@/auth/AuthProvider';
import { Button, Card, ChoiceChips, ErrorState, LoadingState, SectionTitle, TextField } from '@/design-system/components';
import { space, type, useTheme } from '@/design-system/tokens';
import { formatDate } from '@/domain/dates';
import { isoToday, nextReferralStates, notFuture, parseDate, REFERRAL_LABELS } from '@/domain/history';
import { can } from '@/domain/permissions';

import { FactRow } from './FactRow';
import { useAction } from './useAction';

type Urgency = 'ROUTINE' | 'URGENT' | 'EMERGENCY';

function dateProblem(input: string, required: boolean): string | undefined {
  if (!input.trim()) return required ? 'Enter a date, for example 04/11/2026' : undefined;
  const iso = parseDate(input);
  if (!iso) return 'Use a real date, for example 04/11/2026';
  return notFuture(iso) ? undefined : 'This date cannot be in the future';
}

export function HistoryPanel({ encId, patientId }: { encId: string; patientId: string }) {
  const t = useTheme();
  const { me } = useAuth();
  const isDoctor = can(me, 'procedure:record');
  const canVaccine = can(me, 'immunisation:record');
  const history = useQuery({ queryKey: ['history', patientId], queryFn: () => getHistory(patientId), gcTime: 0 });
  const refresh = () => void history.refetch();

  const [procName, setProcName] = useState('');
  const [procDate, setProcDate] = useState(isoToday());
  const [procSite, setProcSite] = useState('');
  const [procOutcome, setProcOutcome] = useState('');
  const procError = dateProblem(procDate, true);
  const saveProc = useAction(
    () => addProcedure(encId, { display: procName.trim(), performed_on: parseDate(procDate) ?? '', body_site: procSite.trim() || undefined, outcome: procOutcome.trim() || undefined }),
    () => { setProcName(''); setProcDate(isoToday()); setProcSite(''); setProcOutcome(''); refresh(); },
  );

  const [vaccine, setVaccine] = useState('');
  const [vDate, setVDate] = useState(isoToday());
  const [dose, setDose] = useState('');
  const [batch, setBatch] = useState('');
  const [nextDue, setNextDue] = useState('');
  const [here, setHere] = useState<'here' | 'elsewhere'>('here');
  const vError = dateProblem(vDate, true);
  const dueIso = parseDate(nextDue);
  const dueError = nextDue.trim() && !dueIso ? 'Use a real date, for example 04/12/2026' : undefined;
  const saveVaccine = useAction(
    () => addImmunisation(encId, {
      vaccine: vaccine.trim(), given_on: parseDate(vDate) ?? '', dose_number: dose ? Number(dose) : undefined,
      batch_number: batch.trim() || undefined, next_due_on: dueIso ?? undefined, given_here: here === 'here',
    }),
    () => { setVaccine(''); setDose(''); setBatch(''); setNextDue(''); refresh(); },
  );

  const [specialty, setSpecialty] = useState('');
  const [toName, setToName] = useState('');
  const [reason, setReason] = useState('');
  const [urgency, setUrgency] = useState<Urgency>('ROUTINE');
  const saveRef = useAction(
    () => addReferral(encId, { to_specialty: specialty.trim(), to_name: toName.trim() || undefined, reason: reason.trim(), urgency }),
    () => { setSpecialty(''); setToName(''); setReason(''); setUrgency('ROUTINE'); refresh(); },
  );
  const move = useAction((id: string, status: string) => updateReferral(id, { status }), refresh);
  const confirm = useAction((kind: string, id: string) => verifyFact(kind, id, 'confirm'), refresh);

  if (history.isPending) return <LoadingState />;
  if (history.isError) return <ErrorState message="Could not load the history." onRetry={() => void history.refetch()} />;
  const h = history.data;
  const canConfirm = can(me, 'fact:verify') && isDoctor;

  return (
    <View style={{ gap: space.md }}>
      <SectionTitle>Procedures</SectionTitle>
      <Card>
        {h.procedures.length === 0 ? <Text style={{ color: t.textMuted }}>None recorded.</Text> : null}
        {h.procedures.map((p) => (
          <FactRow key={p.id} title={p.display}
            detail={[formatDate(p.performed_on), p.body_site, p.outcome, p.complications ? `Complication: ${p.complications}` : null].filter(Boolean).join(' · ')}
            source={p.source} verification={p.verification_state}
            onConfirm={canConfirm ? () => void confirm.run('procedures', p.id) : undefined} />
        ))}
      </Card>
      {isDoctor ? (
        <Card title="Add a procedure">
          <TextField label="Procedure" value={procName} onChangeText={setProcName} />
          <TextField label="Date performed" value={procDate} onChangeText={setProcDate} error={procDate ? procError : undefined} />
          <TextField label="Body site (optional)" value={procSite} onChangeText={setProcSite} />
          <TextField label="Outcome (optional)" value={procOutcome} onChangeText={setProcOutcome} />
          <Button title="Save procedure" disabled={procName.trim().length < 2 || !!procError} loading={saveProc.pending} onPress={() => void saveProc.run()} />
        </Card>
      ) : null}

      <SectionTitle>Vaccines</SectionTitle>
      <Card>
        {h.immunisations.length === 0 ? <Text style={{ color: t.textMuted }}>None recorded.</Text> : null}
        {h.immunisations.map((i) => (
          <FactRow key={i.id} title={`${i.vaccine}${i.dose_number ? ` · dose ${i.dose_number}` : ''}`}
            detail={[formatDate(i.given_on), i.given_here ? 'Given here' : 'Given elsewhere', i.batch_number ? `Batch ${i.batch_number}` : null, i.next_due_on ? `Next due ${formatDate(i.next_due_on)}` : null].filter(Boolean).join(' · ')}
            source={i.source} verification={i.verification_state}
            onConfirm={canConfirm ? () => void confirm.run('immunisations', i.id) : undefined} />
        ))}
      </Card>
      {canVaccine ? (
        <Card title="Add a vaccine">
          <TextField label="Vaccine" value={vaccine} onChangeText={setVaccine} />
          <ChoiceChips value={here} onChange={setHere} options={[{ value: 'here', label: 'Given here' }, { value: 'elsewhere', label: 'Given elsewhere' }]} />
          <TextField label="Date given" value={vDate} onChangeText={setVDate} error={vDate ? vError : undefined} />
          <TextField label="Dose number (optional)" value={dose} onChangeText={(x) => setDose(x.replace(/\D/g, '').slice(0, 2))} keyboardType="number-pad" />
          <TextField label="Batch number (optional)" value={batch} onChangeText={setBatch} />
          <TextField label="Next dose due (optional)" value={nextDue} onChangeText={setNextDue} error={dueError} />
          <Button title="Save vaccine" disabled={vaccine.trim().length < 2 || !!vError || !!dueError} loading={saveVaccine.pending} onPress={() => void saveVaccine.run()} />
          {h.immunisations.length === 0 && !isDoctor ? <Text style={[type.caption, { color: t.textMuted }]}>A doctor confirms what you record.</Text> : null}
        </Card>
      ) : null}

      <SectionTitle>Referrals</SectionTitle>
      <Card>
        {h.referrals.length === 0 ? <Text style={{ color: t.textMuted }}>None recorded.</Text> : null}
        {h.referrals.map((r) => (
          <View key={r.id}>
            <FactRow title={`${r.to_specialty}${r.to_name ? ` · ${r.to_name}` : ''}`}
              detail={`${REFERRAL_LABELS[r.status] ?? r.status}${r.urgency !== 'ROUTINE' ? ` · ${r.urgency.toLowerCase()}` : ''} · ${r.reason}${r.outcome_note ? ` · ${r.outcome_note}` : ''}`}
              source={r.source} verification={r.verification_state} />
            {isDoctor ? (
              <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
                {nextReferralStates(r.status).map((s) => (
                  <Button key={s} size="sm" variant="secondary" title={`Mark ${(REFERRAL_LABELS[s] ?? s).toLowerCase()}`} loading={move.pending}
                    onPress={() => Alert.alert(`Mark referral ${(REFERRAL_LABELS[s] ?? s).toLowerCase()}?`, r.to_specialty, [
                      { text: 'Not yet', style: 'cancel' },
                      { text: 'Yes', onPress: () => void move.run(r.id, s) },
                    ])} />
                ))}
              </View>
            ) : null}
          </View>
        ))}
      </Card>
      {isDoctor ? (
        <Card title="Refer the patient">
          <TextField label="Specialty or service" value={specialty} onChangeText={setSpecialty} />
          <TextField label="Doctor or hospital (optional)" value={toName} onChangeText={setToName} />
          <TextField label="Reason for referral" value={reason} onChangeText={setReason} multiline />
          <ChoiceChips label="How soon?" value={urgency} onChange={setUrgency}
            options={[{ value: 'ROUTINE', label: 'Routine' }, { value: 'URGENT', label: 'Urgent' }, { value: 'EMERGENCY', label: 'Emergency' }]} />
          <Button title="Save referral" disabled={specialty.trim().length < 2 || reason.trim().length < 3} loading={saveRef.pending} onPress={() => void saveRef.run()} />
        </Card>
      ) : null}
    </View>
  );
}
