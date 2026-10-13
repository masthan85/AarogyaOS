import type { ReactNode } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  type TextInputProps,
  View,
} from 'react-native';

import { MIN_TOUCH, radius, space, useTheme } from './tokens';

export function Button({
  title,
  onPress,
  loading,
  disabled,
  variant = 'primary',
}: {
  title: string;
  onPress: () => void;
  loading?: boolean;
  disabled?: boolean;
  variant?: 'primary' | 'secondary' | 'danger';
}) {
  const t = useTheme();
  const bg = variant === 'primary' ? t.primary : variant === 'danger' ? t.danger : 'transparent';
  const fg = variant === 'primary' ? t.primaryText : variant === 'danger' ? '#fff' : t.primary;
  const off = disabled || loading;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!off, busy: !!loading }}
      onPress={onPress}
      disabled={off}
      style={[
        styles.button,
        { backgroundColor: bg, borderColor: t.primary, opacity: off ? 0.6 : 1 },
      ]}>
      {loading ? <ActivityIndicator color={fg} /> : <Text style={[styles.buttonText, { color: fg }]}>{title}</Text>}
    </Pressable>
  );
}

export function TextField({
  label,
  error,
  ...props
}: TextInputProps & { label: string; error?: string }) {
  const t = useTheme();
  return (
    <View style={{ gap: space.xs }}>
      <Text style={{ color: t.text, fontWeight: '600' }}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        placeholderTextColor={t.textMuted}
        style={[
          styles.input,
          { color: t.text, borderColor: error ? t.danger : t.border, backgroundColor: t.surface },
        ]}
        {...props}
      />
      {error ? <Text style={{ color: t.danger }}>{error}</Text> : null}
    </View>
  );
}

export function Card({ children, title }: { children?: ReactNode; title?: string }) {
  const t = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: t.surface, borderColor: t.border }]}>
      {title ? <Text style={{ color: t.text, fontSize: 17, fontWeight: '700' }}>{title}</Text> : null}
      {children}
    </View>
  );
}

export type ChipTone = 'neutral' | 'success' | 'warning' | 'danger' | 'ai';

export function StatusChip({ label, tone = 'neutral' }: { label: string; tone?: ChipTone }) {
  const t = useTheme();
  const colour = { neutral: t.textMuted, success: t.success, warning: t.warning, danger: t.danger, ai: t.ai }[tone];
  return (
    <View style={[styles.chip, { borderColor: colour }]}>
      <Text style={{ color: colour, fontWeight: '600', fontSize: 13 }}>{label}</Text>
    </View>
  );
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  const t = useTheme();
  return (
    <View style={styles.center} accessibilityLiveRegion="polite">
      <ActivityIndicator color={t.primary} />
      <Text style={{ color: t.textMuted }}>{label}</Text>
    </View>
  );
}

export function EmptyState({ message }: { message: string }) {
  const t = useTheme();
  return (
    <View style={styles.center}>
      <Text style={{ color: t.textMuted, textAlign: 'center' }}>{message}</Text>
    </View>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const t = useTheme();
  return (
    <View style={styles.center} accessibilityRole="alert">
      <Text style={{ color: t.danger, textAlign: 'center' }}>{message}</Text>
      {onRetry ? <Button title="Try again" variant="secondary" onPress={onRetry} /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: MIN_TOUCH,
    borderRadius: radius.md,
    borderWidth: 1.5,
    paddingHorizontal: space.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonText: { fontSize: 16, fontWeight: '700' },
  input: {
    minHeight: MIN_TOUCH,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    fontSize: 16,
  },
  card: { borderWidth: 1, borderRadius: radius.lg, padding: space.md, gap: space.sm },
  chip: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4, alignSelf: 'flex-start' },
  center: { padding: space.lg, alignItems: 'center', gap: space.sm },
});

export function ChoiceChips<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label?: string;
  options: { value: T; label: string }[];
  value: T | undefined;
  onChange: (v: T) => void;
}) {
  const t = useTheme();
  return (
    <View style={{ gap: space.xs }}>
      {label ? <Text style={{ color: t.text, fontWeight: '600' }}>{label}</Text> : null}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
        {options.map((o) => {
          const selected = o.value === value;
          return (
            <Pressable
              key={o.value}
              accessibilityRole="radio"
              accessibilityState={{ selected }}
              onPress={() => onChange(o.value)}
              style={{
                minHeight: MIN_TOUCH,
                paddingHorizontal: space.md,
                justifyContent: 'center',
                borderRadius: 999,
                borderWidth: 1.5,
                borderColor: t.primary,
                backgroundColor: selected ? t.primary : 'transparent',
              }}>
              <Text style={{ color: selected ? t.primaryText : t.primary, fontWeight: '600' }}>{o.label}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}
