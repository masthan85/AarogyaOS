import { Platform } from 'react-native';

/**
 * Marks the link to the page being shown. Browsers and their screen readers use aria-current; React
 * Native has no such prop, so on phones the `aria-selected` beside it carries the same meaning.
 */
export function currentPage(active: boolean): Record<string, string> {
  return Platform.OS === 'web' && active ? { 'aria-current': 'page' } : {};
}
