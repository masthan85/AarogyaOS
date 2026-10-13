import { zodResolver } from '@hookform/resolvers/zod';
import { useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { ScrollView, Text, View } from 'react-native';
import { z } from 'zod';

import { ApiError } from '@/api/client';
import { type NewPatient, registerPatient } from '@/api/endpoints';
import { type DuplicateCandidate, duplicateCandidateSchema } from '@/api/schemas';
import { Button, Card, ChoiceChips, TextField } from '@/design-system/components';
import { space, useTheme } from '@/design-system/tokens';
import { LANGUAGE_OPTIONS } from '@/domain/languages';
import { normaliseIndianMobile } from '@/domain/phone';

const schema = z
  .object({
    full_name: z.string().trim().min(2, 'Enter the patient’s full name'),
    age: z.string().trim().optional(),
    dob: z.string().trim().optional(),
    gender: z.enum(['male', 'female', 'other', 'unknown']),
    mobile: z
      .string()
      .trim()
      .optional()
      .refine((v) => !v || normaliseIndianMobile(v) !== null, 'Enter a valid 10-digit mobile number'),
    address: z.string().trim().optional(),
    language: z.string(),
  })
  .superRefine((v, ctx) => {
    const age = v.age ? Number(v.age) : undefined;
    if (v.dob) {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(v.dob)) ctx.addIssue({ code: 'custom', path: ['dob'], message: 'Use YYYY-MM-DD' });
    } else if (age === undefined || !Number.isInteger(age) || age < 0 || age > 120) {
      ctx.addIssue({ code: 'custom', path: ['age'], message: 'Enter age in years (or a date of birth)' });
    }
  });
type Form = z.infer<typeof schema>;

export function NewPatientScreen() {
  const t = useTheme();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [duplicates, setDuplicates] = useState<DuplicateCandidate[]>([]);
  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: { full_name: '', age: '', dob: '', gender: 'unknown', mobile: '', address: '', language: 'en-IN' },
  });

  const submit = async (v: Form, confirm: boolean) => {
    setError(null);
    const body: NewPatient = {
      full_name: v.full_name,
      administrative_gender: v.gender,
      preferred_language: v.language,
      mobile: v.mobile || undefined,
      address: v.address || undefined,
      ...(v.dob ? { date_of_birth: v.dob } : { age_years: Number(v.age) }),
      confirm_not_duplicate: confirm,
    };
    try {
      const created = await registerPatient(body);
      qc.removeQueries({ queryKey: ['patient-search'] });
      router.replace(`/patients/${created.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && err.body?.candidates) {
        setDuplicates(z.array(duplicateCandidateSchema).parse(err.body.candidates));
      } else {
        setError(err instanceof ApiError ? err.message : 'Cannot reach the server. Nothing was saved.');
      }
    }
  };

  const onSubmit = handleSubmit((v) => submit(v, false));

  return (
    <ScrollView contentContainerStyle={{ padding: space.md, gap: space.md }} keyboardShouldPersistTaps="handled">
      {duplicates.length > 0 ? (
        <Card title="This person may already be registered">
          <Text style={{ color: t.textMuted }}>Check these before creating a new record.</Text>
          {duplicates.map((d) => (
            <View key={d.id} style={{ gap: space.xs, paddingVertical: space.sm }}>
              <Text style={{ color: t.text, fontWeight: '700' }}>
                {d.full_name} · {d.mrn}
              </Text>
              <Text style={{ color: t.textMuted }}>
                {d.age_years ?? '?'} yrs · {d.administrative_gender} · {d.reasons.join(', ')}
              </Text>
              <Button title="Open this patient" variant="secondary" onPress={() => router.replace(`/patients/${d.id}`)} />
            </View>
          ))}
          <Button
            title="They are different people — register anyway"
            onPress={handleSubmit((v) => submit(v, true))}
            loading={isSubmitting}
          />
        </Card>
      ) : null}

      <Controller control={control} name="full_name" render={({ field }) => (
        <TextField label="Full name" autoCapitalize="words" value={field.value} onChangeText={field.onChange} error={errors.full_name?.message} />
      )} />
      <View style={{ flexDirection: 'row', gap: space.md }}>
        <View style={{ flex: 1 }}>
          <Controller control={control} name="age" render={({ field }) => (
            <TextField label="Age (years)" keyboardType="number-pad" value={field.value} onChangeText={field.onChange} error={errors.age?.message} />
          )} />
        </View>
        <View style={{ flex: 1 }}>
          <Controller control={control} name="dob" render={({ field }) => (
            <TextField label="or Date of birth" placeholder="YYYY-MM-DD" value={field.value} onChangeText={field.onChange} error={errors.dob?.message} />
          )} />
        </View>
      </View>
      <Controller control={control} name="gender" render={({ field }) => (
        <ChoiceChips label="Gender" value={field.value} onChange={field.onChange} options={[
          { value: 'female', label: 'Female' }, { value: 'male', label: 'Male' },
          { value: 'other', label: 'Other' }, { value: 'unknown', label: 'Not stated' },
        ]} />
      )} />
      <Controller control={control} name="mobile" render={({ field }) => (
        <TextField label="Mobile number" keyboardType="phone-pad" value={field.value} onChangeText={field.onChange} error={errors.mobile?.message} />
      )} />
      <Controller control={control} name="address" render={({ field }) => (
        <TextField label="Address" value={field.value} onChangeText={field.onChange} multiline />
      )} />
      <Controller control={control} name="language" render={({ field }) => (
        <ChoiceChips label="Preferred language" value={field.value} onChange={field.onChange}
          options={LANGUAGE_OPTIONS.map((l) => ({ value: l.tag, label: l.label }))} />
      )} />

      {error ? <Text accessibilityRole="alert" style={{ color: t.danger }}>{error}</Text> : null}
      <Button title="Register patient" onPress={onSubmit} loading={isSubmitting && duplicates.length === 0} />
      <Text style={{ color: t.textMuted }}>
        Mobile numbers can be shared by a family; only name and date of birth decide duplicates.
      </Text>
    </ScrollView>
  );
}
