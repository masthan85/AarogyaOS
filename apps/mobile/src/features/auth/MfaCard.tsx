import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Alert, Text, View } from 'react-native';

import { ApiError } from '@/api/client';
import { confirmMfa, disableMfa, getMfaStatus, startMfaEnrolment } from '@/api/endpoints';
import { Button, Card, TextField } from '@/design-system/components';
import { space, type, useTheme } from '@/design-system/tokens';
import { groupSecret, looksLikeCode, tidyCode } from '@/domain/mfa';

const fail = (title: string) => (e: unknown) => Alert.alert(title, e instanceof ApiError ? e.message : 'Check your connection.');

/** Two-step sign-in with an authenticator app. The secret is shown as text; there is no QR code. */
export function MfaCard() {
  const t = useTheme();
  const status = useQuery({ queryKey: ['mfa'], queryFn: getMfaStatus, gcTime: 0 });
  const [enrol, setEnrol] = useState<{ secret: string; uri: string } | null>(null);
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [codes, setCodes] = useState<string[] | null>(null);
  const [turningOff, setTurningOff] = useState(false);

  const start = useMutation({
    mutationFn: startMfaEnrolment,
    onSuccess: (r) => { setEnrol({ secret: r.secret, uri: r.otpauth_uri }); setCode(''); },
    onError: fail('Could not start'),
  });
  const confirm = useMutation({
    mutationFn: () => confirmMfa(tidyCode(code)),
    onSuccess: (r) => { setCodes(r.recovery_codes); setEnrol(null); setCode(''); void status.refetch(); },
    onError: fail('That did not work'),
  });
  const off = useMutation({
    mutationFn: () => disableMfa({ password, code: tidyCode(code) }),
    onSuccess: () => { setTurningOff(false); setPassword(''); setCode(''); void status.refetch(); },
    onError: fail('Could not turn it off'),
  });

  if (status.isPending) return <Card title="Two-step sign-in"><Text style={{ color: t.textMuted }}>Loading…</Text></Card>;
  if (status.isError) return <Card title="Two-step sign-in"><Text style={{ color: t.textMuted }}>Could not load. Try again later.</Text></Card>;

  if (codes) {
    return (
      <Card title="Save your recovery codes">
        <Text style={[type.small, { color: t.textMuted }]}>
          Each code works once if you lose your phone. They are shown only now: write them down or store them in a password manager.
        </Text>
        {codes.map((c) => <Text key={c} selectable style={[type.body, { color: t.text, fontVariant: ['tabular-nums'] }]}>{c}</Text>)}
        <Button title="I have saved them" onPress={() => setCodes(null)} />
      </Card>
    );
  }

  if (enrol) {
    return (
      <Card title="Set up two-step sign-in">
        <Text style={[type.small, { color: t.textMuted }]}>
          In your authenticator app choose "enter a setup key" and type this key (time-based, 6 digits), then enter the code the app shows.
        </Text>
        <Text selectable style={[type.h3, { color: t.text }]}>{groupSecret(enrol.secret)}</Text>
        <TextField label="Code from the app" keyboardType="number-pad" value={code} onChangeText={setCode} />
        <Button title="Turn on" loading={confirm.isPending} disabled={!looksLikeCode(code)} onPress={() => confirm.mutate()} />
        <Button title="Cancel" variant="ghost" onPress={() => setEnrol(null)} />
      </Card>
    );
  }

  if (status.data.enabled) {
    return (
      <Card title="Two-step sign-in">
        <Text style={{ color: t.success, fontWeight: '700' }}>On</Text>
        <Text style={[type.small, { color: t.textMuted }]}>{status.data.recovery_codes_remaining} recovery codes left.</Text>
        {turningOff ? (
          <View style={{ gap: space.sm }}>
            <TextField label="Your password" secureTextEntry autoCapitalize="none" value={password} onChangeText={setPassword} />
            <TextField label="Code from the app, or a recovery code" autoCapitalize="none" value={code} onChangeText={setCode} />
            <Button title="Turn off" variant="danger" loading={off.isPending} disabled={!password || !looksLikeCode(code)} onPress={() => off.mutate()} />
            <Button title="Keep it on" variant="ghost" onPress={() => setTurningOff(false)} />
          </View>
        ) : (
          <Button title="Turn off" variant="secondary" onPress={() => setTurningOff(true)} />
        )}
      </Card>
    );
  }

  return (
    <Card title="Two-step sign-in">
      <Text style={[type.small, { color: t.textMuted }]}>Off. Turning it on asks for a code from an authenticator app each time you sign in.</Text>
      <Button title="Set up" loading={start.isPending} onPress={() => start.mutate()} />
    </Card>
  );
}
