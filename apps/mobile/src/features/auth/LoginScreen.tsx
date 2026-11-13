import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, Text, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { z } from 'zod';

import { ApiError } from '@/api/client';
import { useAuth } from '@/auth/AuthProvider';
import { Button, Card, TextField } from '@/design-system/components';
import { needsSecondFactor, tidyCode, wrongSecondFactor } from '@/domain/mfa';
import { displayFont, layout, MIN_TOUCH_SMALL, radius, space, type, useTheme } from '@/design-system/tokens';

const formSchema = z.object({
  organisationSlug: z.string().trim().toLowerCase().optional(),
  email: z.string().trim().min(1, 'Enter your email address').email('Enter a valid email address'),
  password: z.string().min(1, 'Enter your password'),
});
type FormValues = z.infer<typeof formSchema>;

export function LoginScreen() {
  const t = useTheme();
  const { signIn } = useAuth();
  const [formError, setFormError] = useState<string | null>(null);
  const [askForCode, setAskForCode] = useState(false);
  const [code, setCode] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const { width } = useWindowDimensions();
  const wide = width >= layout.wide;
  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: { organisationSlug: '', email: '', password: '' },
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await signIn({ ...values, mfaCode: askForCode ? tidyCode(code) : undefined });
    } catch (err) {
      if (needsSecondFactor(err)) {
        setAskForCode(true);
        setFormError('Enter the 6-digit code from your authenticator app, or one of your recovery codes.');
      } else if (wrongSecondFactor(err)) setFormError('That code is not right. Check the time on your phone, or use a recovery code.');
      else if (err instanceof ApiError && err.status === 401) setFormError('Email, password or organisation is incorrect.');
      else if (err instanceof ApiError) setFormError(err.message);
      else setFormError('Cannot reach the server. Check your connection and try again.');
    }
  });

  const mark = (onHero: boolean) => (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
      <View
        accessibilityElementsHidden
        style={{ width: 44, height: 44, borderRadius: radius.md, backgroundColor: onHero ? t.heroText : t.hero, alignItems: 'center', justifyContent: 'center' }}>
        <Text style={{ color: onHero ? t.hero : t.heroText, fontSize: 24, fontWeight: '700', fontFamily: displayFont }}>A</Text>
      </View>
      <Text style={{ color: onHero ? t.heroText : t.text, fontSize: 22, fontWeight: '700', fontFamily: displayFont }}>AarogyaOS</Text>
    </View>
  );

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.background, flexDirection: wide ? 'row' : 'column' }}>
      {wide ? (
        <View style={{ flex: 1, maxWidth: 640, backgroundColor: t.hero, padding: 56, justifyContent: 'space-between' }}>
          {mark(true)}
          <View style={{ gap: space.md, maxWidth: 440 }}>
            <Text style={{ color: t.heroText, fontSize: 44, lineHeight: 50, fontWeight: '700', letterSpacing: -0.8, fontFamily: displayFont }}>
              Software proposes.{'\n'}The doctor decides.
            </Text>
            <Text style={{ color: t.heroMuted, fontSize: 18, lineHeight: 28 }}>
              One record for reception, nursing, consultation, pharmacy and billing. Anything software suggests stays marked as a suggestion until a clinician accepts it.
            </Text>
          </View>
          <Text style={[type.small, { color: t.heroMuted }]}>Sign in only on a device your clinic trusts.</Text>
        </View>
      ) : null}
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: 'center', padding: space.lg }}>
          <View style={{ width: '100%', maxWidth: wide ? layout.form : 480, alignSelf: 'center', gap: space.lg }}>
            {wide ? null : mark(false)}
            <View style={{ gap: space.xs }}>
              <Text accessibilityRole="header" style={[type.display, { color: t.text }]}>Sign in</Text>
              <Text style={[type.body, { color: t.textMuted }]}>Use the account your clinic gave you.</Text>
            </View>
            <Card>
            <Controller
              control={control}
              name="organisationSlug"
              render={({ field }) => (
                <TextField
                  label="Organisation"
                  placeholder="sunrise-clinic"
                  autoCapitalize="none"
                  autoCorrect={false}
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                />
              )}
            />
            <Controller
              control={control}
              name="email"
              render={({ field }) => (
                <TextField
                  label="Email"
                  autoCapitalize="none"
                  autoComplete="email"
                  keyboardType="email-address"
                  textContentType="username"
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={errors.email?.message}
                />
              )}
            />
            <Controller
              control={control}
              name="password"
              render={({ field }) => (
                <TextField
                  label="Password"
                  secureTextEntry={!showPassword}
                  autoCapitalize="none"
                  autoComplete="password"
                  textContentType="password"
                  value={field.value}
                  onChangeText={field.onChange}
                  onBlur={field.onBlur}
                  error={errors.password?.message}
                />
              )}
            />
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={showPassword ? 'Hide password' : 'Show password'}
              onPress={() => setShowPassword((v) => !v)}
              style={{ alignSelf: 'flex-end', minHeight: MIN_TOUCH_SMALL, justifyContent: 'center', marginTop: -space.xs }}>
              <Text style={[type.small, { color: t.primary, fontWeight: '700' }]}>{showPassword ? 'Hide password' : 'Show password'}</Text>
            </Pressable>
            {askForCode ? (
              <TextField label="Verification code" keyboardType="default" autoCapitalize="none" autoCorrect={false}
                autoComplete="one-time-code" textContentType="oneTimeCode" value={code} onChangeText={setCode} />
            ) : null}
            {formError ? (
              <Text accessibilityRole="alert" style={[type.small, { color: t.danger }]}>
                {formError}
              </Text>
            ) : null}
            <Button title="Sign in" onPress={onSubmit} loading={isSubmitting} block />
            </Card>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
