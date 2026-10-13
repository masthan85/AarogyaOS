import { useColorScheme } from 'react-native';

const light = {
  background: '#F6F8FA',
  surface: '#FFFFFF',
  text: '#0F1B2D',
  textMuted: '#52607A',
  border: '#D5DCE6',
  primary: '#0B6E6E',
  primaryText: '#FFFFFF',
  danger: '#B3261E',
  warning: '#8A5A00',
  success: '#1B6B3A',
  ai: '#5B3FA6',
};

const dark: typeof light = {
  background: '#0B1220',
  surface: '#141D2E',
  text: '#EAF0F8',
  textMuted: '#9AA8BF',
  border: '#2A3650',
  primary: '#4FC3C3',
  primaryText: '#06201F',
  danger: '#F2B8B5',
  warning: '#F5C97A',
  success: '#8FD6A8',
  ai: '#C7B6F2',
};

export type Theme = typeof light;
export const useTheme = (): Theme => (useColorScheme() === 'dark' ? dark : light);

export const space = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 } as const;
export const radius = { md: 12, lg: 16 } as const;
/** Clinical staff work fast, often gloved: keep touch targets generous. */
export const MIN_TOUCH = 48;
