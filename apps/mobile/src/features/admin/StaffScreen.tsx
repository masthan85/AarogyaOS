import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';

import { createPractitioner, createUser, deactivateUser, getFacilities, getPractitionersFull, getRoles, getUsers, setWorkingHours } from '@/api/endpoints';
import type { PractitionerFull, StaffUser } from '@/api/schemas';
import { Button, Card, ChoiceChips, EmptyState, LoadingState, MultiChips, SectionTitle, StatusChip, TextField } from '@/design-system/components';
import { space, useTheme, type } from '@/design-system/tokens';
import { describeHours, emailProblem, hoursFor, isDoctorUser, passwordProblem, timeProblem, WEEKDAYS } from '@/domain/admin';
import { roleLabel } from '@/domain/permissions';
import { useAction } from '@/features/consultation/useAction';

export function StaffScreen() {
  const t = useTheme();
  const qc = useQueryClient();
  const users = useQuery({ queryKey: ['users'], queryFn: getUsers, gcTime: 0 });
  const roles = useQuery({ queryKey: ['roles'], queryFn: getRoles });
  const pracs = useQuery({ queryKey: ['practitioners-full'], queryFn: getPractitionersFull, gcTime: 0 });
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['users'] });
    void qc.invalidateQueries({ queryKey: ['practitioners-full'] });
  };
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('nurse');
  const problem = (email && emailProblem(email)) || (password && passwordProblem(password)) || null;
  const add = useAction(
    () => createUser({ email: email.trim().toLowerCase(), full_name: name.trim(), password, roles: [role] }),
    () => { setEmail(''); setName(''); setPassword(''); refresh(); },
  );
  if (users.isPending) return <LoadingState label="Loading staff…" />;
  const profileOf = (u: StaffUser) => pracs.data?.find((p) => p.user_id === u.id);

  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }} keyboardShouldPersistTaps="handled">
      <SectionTitle>Staff</SectionTitle>
      {users.data?.length === 0 ? <EmptyState message="No staff yet." /> : null}
      {users.data?.map((u) => <UserCard key={u.id} user={u} profile={profileOf(u)} onChanged={refresh} />)}

      <Card title="Add a staff member">
        <TextField label="Full name" value={name} onChangeText={setName} />
        <TextField label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" />
        <TextField label="Temporary password (12+ characters)" value={password} onChangeText={setPassword} secureTextEntry autoCapitalize="none" />
        <ChoiceChips label="Role" value={role} onChange={setRole}
          options={(roles.data ?? []).filter((r) => r.key !== 'super_admin').map((r) => ({ value: r.key, label: roleLabel(r.key) }))} />
        {problem ? <Text style={{ color: t.danger }}>{problem}</Text> : null}
        <Button title="Add" disabled={!name.trim() || !!emailProblem(email) || !!passwordProblem(password)} loading={add.pending} onPress={() => void add.run()} />
        <Text style={[type.caption, { color: t.textMuted }]}>Tell them the password in person and ask them to change it. Doctors also need a profile below before they can be booked.</Text>
      </Card>
    </ScrollView>
  );
}

function UserCard({ user, profile, onChanged }: { user: StaffUser; profile?: PractitionerFull; onChanged: () => void }) {
  const t = useTheme();
  const deactivate = useAction(() => deactivateUser(user.id), onChanged);
  return (
    <Card>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, alignItems: 'center' }}>
        <Text style={{ color: t.text, fontWeight: '700', flexShrink: 1 }}>{user.full_name}</Text>
        {user.roles.map((r) => <StatusChip key={r} label={roleLabel(r)} />)}
        {!user.is_active ? <StatusChip label="Deactivated" tone="warning" /> : null}
      </View>
      <Text style={{ color: t.textMuted }}>{user.email}</Text>
      {isDoctorUser(user) ? <DoctorProfile user={user} profile={profile} onChanged={onChanged} /> : null}
      {user.is_active ? (
        <Button title="Deactivate account" variant="secondary" loading={deactivate.pending}
          onPress={() => Alert.alert('Deactivate this account?', `${user.full_name} will be signed out and unable to sign in.`, [
            { text: 'Keep', style: 'cancel' }, { text: 'Deactivate', style: 'destructive', onPress: () => void deactivate.run() }])} />
      ) : null}
    </Card>
  );
}

function DoctorProfile({ user, profile, onChanged }: { user: StaffUser; profile?: PractitionerFull; onChanged: () => void }) {
  const t = useTheme();
  const facilities = useQuery({ queryKey: ['facilities'], queryFn: getFacilities });
  const [facility, setFacility] = useState<string | undefined>(profile?.facility_id);
  const [specialty, setSpecialty] = useState('General medicine');
  const [reg, setReg] = useState('');
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4]);
  const [start, setStart] = useState('09:00');
  const [end, setEnd] = useState('17:00');
  const create = useAction(
    () => createPractitioner({ user_id: user.id, facility_id: facility as string, specialty: specialty.trim(), registration_number: reg.trim() || undefined }),
    onChanged,
  );
  const hours = useAction(() => setWorkingHours((profile as PractitionerFull).id, hoursFor(days, start, end)), onChanged);
  const hoursProblem = timeProblem(start, end);

  if (!profile) {
    return (
      <View style={{ gap: space.sm }}>
        <Text style={{ color: t.warning }}>No doctor profile yet, so this doctor cannot be booked.</Text>
        <ChoiceChips label="Site" value={facility} onChange={setFacility} options={(facilities.data ?? []).map((f) => ({ value: f.id, label: f.name }))} />
        <TextField label="Specialty" value={specialty} onChangeText={setSpecialty} />
        <TextField label="Registration number (recorded, not verified)" value={reg} onChangeText={setReg} autoCapitalize="characters" />
        <Button title="Create doctor profile" disabled={!facility || specialty.trim().length < 2} loading={create.pending} onPress={() => void create.run()} />
      </View>
    );
  }
  return (
    <View style={{ gap: space.sm }}>
      <Text style={{ color: t.textMuted }}>{profile.specialty}{profile.registration_number ? ` · reg. ${profile.registration_number} (not verified)` : ''}</Text>
      <Text style={{ color: profile.working_hours.length ? t.text : t.warning }}>{describeHours(profile.working_hours)}</Text>
      <MultiChips label="Working days" value={days} onChange={setDays} options={WEEKDAYS.map((d, i) => ({ value: i, label: d }))} />
      <TextField label="From (HH:MM)" value={start} onChangeText={setStart} />
      <TextField label="To (HH:MM)" value={end} onChangeText={setEnd} />
      {hoursProblem ? <Text style={{ color: t.danger }}>{hoursProblem}</Text> : null}
      <Button title="Save working hours" variant="secondary" disabled={!!hoursProblem || days.length === 0} loading={hours.pending} onPress={() => void hours.run()} />
    </View>
  );
}
