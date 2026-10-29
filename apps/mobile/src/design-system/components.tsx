import type { ReactNode } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Switch,
  StyleSheet,
  Text,
  TextInput,
  type TextInputProps,
  View,
} from 'react-native';

import { elevation, MIN_TOUCH, MIN_TOUCH_SMALL, radius, space, type, useIsDark, useTheme } from './tokens';

export function Button({
  title,
  onPress,
  loading,
  disabled,
  variant = 'primary',
  size = 'md',
}: {
  title: string;
  onPress: () => void;
  loading?: boolean;
  disabled?: boolean;
  /** primary: the one main action. secondary: a quiet tinted button. ghost: text only. danger: destructive. */
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'md' | 'sm';
}) {
  const t = useTheme();
  const bg = { primary: t.primary, secondary: t.primarySoft, ghost: 'transparent', danger: t.danger }[variant];
  const fg = { primary: t.primaryText, secondary: t.primary, ghost: t.primary, danger: t.dangerText }[variant];
  const off = disabled || loading;
  const small = size === 'sm';
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!off, busy: !!loading }}
      onPress={onPress}
      disabled={off}
      style={({ pressed }) => [
        styles.button,
        small && styles.buttonSmall,
        { backgroundColor: bg, opacity: off ? 0.55 : pressed ? 0.85 : 1 },
      ]}>
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <Text style={[styles.buttonText, small && { fontSize: 14 }, { color: fg }]}>{title}</Text>
      )}
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
      <Text style={[type.small, { color: t.text, fontWeight: '600' }]}>{label}</Text>
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

export function Card({
  children,
  title,
  tone = 'default',
}: {
  children?: ReactNode;
  title?: string;
  /** ai: software-suggested content; warning and danger: needs attention. A coloured edge plus a tint, never colour alone. */
  tone?: 'default' | 'ai' | 'warning' | 'danger';
}) {
  const t = useTheme();
  const dark = useIsDark();
  const accent = { default: null, ai: t.ai, warning: t.warning, danger: t.danger }[tone];
  const tint = { default: t.surface, ai: t.aiSoft, warning: t.warningSoft, danger: t.dangerSoft }[tone];
  return (
    <View
      style={[
        styles.card,
        elevation(dark),
        { backgroundColor: tint, borderColor: accent ?? t.border },
        accent ? { borderLeftWidth: 4 } : null,
      ]}>
      {title ? <Text style={[type.h3, { color: t.text }]}>{title}</Text> : null}
      {children}
    </View>
  );
}

export type ChipTone = 'neutral' | 'success' | 'warning' | 'danger' | 'ai';

export function StatusChip({ label, tone = 'neutral' }: { label: string; tone?: ChipTone }) {
  const t = useTheme();
  const fg = { neutral: t.textMuted, success: t.success, warning: t.warning, danger: t.danger, ai: t.ai }[tone];
  const bg = { neutral: t.neutralSoft, success: t.successSoft, warning: t.warningSoft, danger: t.dangerSoft, ai: t.aiSoft }[tone];
  return (
    <View style={[styles.chip, { backgroundColor: bg }]}>
      <Text style={{ color: fg, fontWeight: '700', fontSize: 12.5 }}>{label}</Text>
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

export function EmptyState({ message, title }: { message: string; title?: string }) {
  const t = useTheme();
  return (
    <View style={[styles.center, { backgroundColor: t.neutralSoft, borderRadius: radius.lg, marginVertical: space.xs }]}>
      {title ? <Text style={[type.h3, { color: t.text, textAlign: 'center' }]}>{title}</Text> : null}
      <Text style={[type.small, { color: t.textMuted, textAlign: 'center' }]}>{message}</Text>
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
    paddingHorizontal: space.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonSmall: { minHeight: MIN_TOUCH_SMALL, paddingHorizontal: 14 },
  buttonText: { fontSize: 16, fontWeight: '700' },
  input: {
    minHeight: MIN_TOUCH,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    fontSize: 16,
  },
  card: { borderWidth: StyleSheet.hairlineWidth * 2, borderRadius: radius.lg, padding: space.md, gap: space.sm },
  chip: { borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 4, alignSelf: 'flex-start' },
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
  // A few short choices read best as one connected control; many or long ones wrap as separate chips.
  const segmented = options.length >= 2 && options.length <= 4 && options.reduce((n, o) => n + o.label.length, 0) <= 30;
  return (
    <View style={{ gap: space.xs }}>
      {label ? <Text style={[type.small, { color: t.text, fontWeight: '600' }]}>{label}</Text> : null}
      {segmented ? (
        <View style={{ flexDirection: 'row', backgroundColor: t.neutralSoft, borderRadius: radius.md, padding: 3, gap: 3 }}>
          {options.map((o) => {
            const selected = o.value === value;
            return (
              <Pressable
                key={o.value}
                accessibilityRole="radio"
                accessibilityState={{ selected }}
                onPress={() => onChange(o.value)}
                style={{
                  flex: 1,
                  minHeight: MIN_TOUCH - 6,
                  paddingHorizontal: 6,
                  alignItems: 'center',
                  justifyContent: 'center',
                  borderRadius: radius.md - 3,
                  backgroundColor: selected ? t.primary : 'transparent',
                }}>
                <Text style={{ color: selected ? t.primaryText : t.text, fontWeight: selected ? '800' : '600', fontSize: 15, textAlign: 'center' }}>{o.label}</Text>
              </Pressable>
            );
          })}
        </View>
      ) : (
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
                  borderColor: selected ? t.primary : t.border,
                  backgroundColor: selected ? t.primary : t.surface,
                }}>
                <Text style={{ color: selected ? t.primaryText : t.text, fontWeight: '600' }}>{o.label}</Text>
              </Pressable>
            );
          })}
        </View>
      )}
    </View>
  );
}

export function AlertBanner({ level, message }: { level: 'CRITICAL' | 'WARNING' | 'INFO'; message: string }) {
  const t = useTheme();
  const colour = level === 'CRITICAL' ? t.danger : level === 'WARNING' ? t.warning : t.textMuted;
  const bg = level === 'CRITICAL' ? t.dangerSoft : level === 'WARNING' ? t.warningSoft : t.neutralSoft;
  return (
    <View
      accessibilityRole="alert"
      style={{ borderLeftWidth: 4, borderLeftColor: colour, backgroundColor: bg, borderRadius: radius.md, padding: space.sm + 2, gap: 2 }}>
      <Text style={[type.caption, { color: colour, textTransform: 'uppercase' }]}>{level === 'INFO' ? 'Note' : level}</Text>
      <Text style={[type.small, { color: t.text }]}>{message}</Text>
    </View>
  );
}

/** Where a clinical fact came from and whether a clinician has checked it. */
export function ProvenanceChip({ text, tone }: { text: string; tone: ChipTone }) {
  return <StatusChip label={text} tone={tone} />;
}

export function SectionTitle({ children }: { children: ReactNode }) {
  const t = useTheme();
  return <Text style={[type.overline, { color: t.textMuted }]}>{children}</Text>;
}

export function MultiChips<T extends string | number>({
  label,
  options,
  value,
  onChange,
}: {
  label?: string;
  options: { value: T; label: string }[];
  value: T[];
  onChange: (v: T[]) => void;
}) {
  const t = useTheme();
  return (
    <View style={{ gap: space.xs }}>
      {label ? <Text style={{ color: t.text, fontWeight: '600' }}>{label}</Text> : null}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: space.sm }}>
        {options.map((o) => {
          const selected = value.includes(o.value);
          return (
            <Pressable
              key={String(o.value)}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: selected }}
              onPress={() => onChange(selected ? value.filter((v) => v !== o.value) : [...value, o.value])}
              style={{
                minHeight: MIN_TOUCH,
                paddingHorizontal: space.md,
                justifyContent: 'center',
                borderRadius: 999,
                borderWidth: 1.5,
                borderColor: selected ? t.primary : t.border,
                backgroundColor: selected ? t.primary : t.surface,
              }}>
              <Text style={{ color: selected ? t.primaryText : t.text, fontWeight: '600' }}>{o.label}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

/** A labelled switch with a sentence saying what it does. */
export function ToggleRow({
  label,
  help,
  value,
  onChange,
  disabled,
}: {
  label: string;
  help?: string;
  value: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  const t = useTheme();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.md, opacity: disabled ? 0.5 : 1 }}>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={{ color: t.text, fontWeight: '600' }}>{label}</Text>
        {help ? <Text style={{ color: t.textMuted, fontSize: 12 }}>{help}</Text> : null}
      </View>
      <Switch value={value} onValueChange={onChange} disabled={disabled} accessibilityLabel={label} />
    </View>
  );
}


/** Circle with the person's initials. Decoration only: the name is always written next to it. */
export function Avatar({ name, size = 44 }: { name: string; size?: number }) {
  const t = useTheme();
  const initials = name
    .replace(/^(dr|mr|mrs|ms)\.?\s+/i, '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join('');
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: t.primarySoft, alignItems: 'center', justifyContent: 'center' }}>
      <Text style={{ color: t.primary, fontWeight: '800', fontSize: size * 0.38 }}>{initials || '?'}</Text>
    </View>
  );
}

/**
 * A row of sections that scrolls sideways, with the current one underlined. Replaces wrapped pills
 * when there are many sections: one line, so the content starts higher on the screen.
 */
export function TabBar<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { value: T; label: string; badge?: number }[];
  value: T;
  onChange: (v: T) => void;
}) {
  const t = useTheme();
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      accessibilityRole="tablist"
      style={{ flexGrow: 0, flexShrink: 0, borderBottomWidth: StyleSheet.hairlineWidth * 2, borderBottomColor: t.border }}
      contentContainerStyle={{ paddingHorizontal: space.md, gap: space.xs }}>
      {tabs.map((tab) => {
        const selected = tab.value === value;
        return (
          <Pressable
            key={tab.value}
            accessibilityRole="tab"
            accessibilityState={{ selected }}
            accessibilityLabel={tab.badge ? `${tab.label}, ${tab.badge} waiting` : tab.label}
            onPress={() => onChange(tab.value)}
            style={{
              minHeight: MIN_TOUCH,
              paddingHorizontal: space.sm + 2,
              flexDirection: 'row',
              alignItems: 'center',
              gap: 6,
              borderBottomWidth: 3,
              borderBottomColor: selected ? t.primary : 'transparent',
            }}>
            <Text style={{ color: selected ? t.primary : t.textMuted, fontWeight: selected ? '800' : '600', fontSize: 15 }}>{tab.label}</Text>
            {tab.badge ? (
              <View style={{ minWidth: 20, height: 20, borderRadius: 10, paddingHorizontal: 6, backgroundColor: t.ai, alignItems: 'center', justifyContent: 'center' }}>
                <Text style={{ color: t.surface, fontWeight: '800', fontSize: 12 }}>{tab.badge}</Text>
              </View>
            ) : null}
          </Pressable>
        );
      })}
    </ScrollView>
  );
}


/** An introductory sentence or two under a screen's title. */
export function Lead({ children }: { children: ReactNode }) {
  const t = useTheme();
  return <Text style={[type.small, { color: t.textMuted, lineHeight: 20 }]}>{children}</Text>;
}

/** A row that opens another screen: title, one line of help, and an arrow. */
export function NavRow({ title, description, onPress }: { title: string; description?: string; onPress: () => void }) {
  const t = useTheme();
  const dark = useIsDark();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={description ? `${title}. ${description}` : title}
      onPress={onPress}
      style={({ pressed }) => [
        styles.card,
        elevation(dark),
        { backgroundColor: t.surface, borderColor: t.border, flexDirection: 'row', alignItems: 'center', gap: space.md, minHeight: MIN_TOUCH, opacity: pressed ? 0.85 : 1 },
      ]}>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[type.h3, { color: t.text }]}>{title}</Text>
        {description ? <Text style={[type.small, { color: t.textMuted }]}>{description}</Text> : null}
      </View>
      <Text style={{ color: t.textMuted, fontSize: 22 }} accessibilityElementsHidden>›</Text>
    </Pressable>
  );
}
