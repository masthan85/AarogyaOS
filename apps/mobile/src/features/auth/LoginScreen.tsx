import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { KeyboardAvoidingView, Platform, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { z } from 'zod';

import { ApiError } from '@/api/client';
import { useAuth } from '@/auth/AuthProvider';
import { Button, Card, TextField } from '@/design-system/components';
import { radius, space, type, useTheme } from '@/design-system/tokens';

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
      await signIn(values);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setFormError('Email, password or organisation is incorrect.');
      else if (err instanceof ApiError) setFormError(err.message);
      else setFormError('Cannot reach the server. Check your connection and try again.');
    }
  });

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.background }}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: 'center', padding: space.lg }}>
          <View style={{ width: '100%', maxWidth: 480, alignSelf: 'center', gap: space.lg }}>
            <View style={{ gap: space.sm }}>
              <View
                accessibilityElementsHidden
                style={{ width: 56, height: 56, borderRadius: radius.lg, backgroundColor: t.hero, alignItems: 'center', justifyContent: 'center' }}>
                <Text style={{ color: t.heroText, fontSize: 28, fontWeight: '800' }}>A</Text>
              </View>
              <Text style={[type.display, { color: t.text }]}>AarogyaOS</Text>
              <Text style={[type.body, { color: t.textMuted }]}>Sign in with your organisation account.</Text>
            </View>
            <Card>
            <Controller
              control={control}
              name="organisationSlug"
              render={({ field }) => (
                <TextField
                  label="Organisation"
                  placeholder="e.g. sunrise-clinic"
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
                  secureTextEntry
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
            {formError ? (
              <Text accessibilityRole="alert" style={[type.small, { color: t.danger }]}>
                {formError}
              </Text>
            ) : null}
            <Button title="Sign in" onPress={onSubmit} loading={isSubmitting} />
            </Card>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
