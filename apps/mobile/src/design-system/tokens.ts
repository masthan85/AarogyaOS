import { Platform, useColorScheme, type ViewStyle } from 'react-native';

/**
 * Colour roles, not colours. Every text/background pairing used by the components was checked against
 * WCAG AA (4.5:1) in both themes. Meaning is never carried by colour alone: states also have words.
 * `*Soft` colours are quiet tints used as backgrounds behind text in the matching strong colour.
 */
const light = {
  background: '#F3F6F8',
  surface: '#FFFFFF',
  text: '#0E1B2C',
  textMuted: '#4E5D75',
  border: '#DCE3EB',
  primary: '#0A6468',
  primaryText: '#FFFFFF',
  danger: '#B3261E',
  dangerText: '#FFFFFF',
  warning: '#8A5A00',
  success: '#1B6B3A',
  ai: '#5B3FA6',
  primarySoft: '#E1F0F0',
  aiSoft: '#EFEAFA',
  warningSoft: '#FBF0D9',
  dangerSoft: '#FBE7E5',
  successSoft: '#E3F2E8',
  neutralSoft: '#EAEFF4',
  hero: '#0A4F53',
  heroText: '#FFFFFF',
  heroMuted: '#BFE3E3',
};

const dark: typeof light = {
  background: '#0A1220',
  surface: '#131C2D',
  text: '#EAF0F8',
  textMuted: '#9AA8BF',
  border: '#26334B',
  primary: '#5CC6C6',
  primaryText: '#06201F',
  danger: '#F2B8B5',
  dangerText: '#410E0B',
  warning: '#F5C97A',
  success: '#8FD6A8',
  ai: '#C7B6F2',
  primarySoft: '#133A3D',
  aiSoft: '#27204A',
  warningSoft: '#3A2E12',
  dangerSoft: '#3C1D1B',
  successSoft: '#14301F',
  neutralSoft: '#1B2740',
  hero: '#0F3F43',
  heroText: '#EAF0F8',
  heroMuted: '#9CC9C9',
};

export type Theme = typeof light;
export const useTheme = (): Theme => (useColorScheme() === 'dark' ? dark : light);
export const useIsDark = (): boolean => useColorScheme() === 'dark';

export const space = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 } as const;
export const radius = { sm: 8, md: 12, lg: 16, pill: 999 } as const;
/** Clinical staff work fast, often gloved: keep touch targets generous. */
export const MIN_TOUCH = 48;
/** Smaller controls (inline actions in a list) never go below the 44-point platform minimum. */
export const MIN_TOUCH_SMALL = 44;

/** One type scale for the whole app, so sizes are decisions rather than accidents. */
export const type = {
  display: { fontSize: 28, fontWeight: '800', letterSpacing: -0.4 },
  title: { fontSize: 22, fontWeight: '800', letterSpacing: -0.2 },
  h2: { fontSize: 18, fontWeight: '700' },
  h3: { fontSize: 16, fontWeight: '700' },
  body: { fontSize: 16, fontWeight: '400' },
  small: { fontSize: 14, fontWeight: '400' },
  caption: { fontSize: 12, fontWeight: '600', letterSpacing: 0.2 },
  overline: { fontSize: 12, fontWeight: '700', letterSpacing: 0.8, textTransform: 'uppercase' },
} as const;

/** A whisper of depth in light mode; dark mode relies on borders alone. */
export function elevation(dark: boolean): ViewStyle {
  if (dark) return {};
  return Platform.select<ViewStyle>({
    ios: { shadowColor: '#0E1B2C', shadowOpacity: 0.06, shadowRadius: 8, shadowOffset: { width: 0, height: 2 } },
    android: { elevation: 1 },
    default: { boxShadow: '0 1px 3px rgba(14,27,44,0.08)' } as ViewStyle,
  }) as ViewStyle;
}
