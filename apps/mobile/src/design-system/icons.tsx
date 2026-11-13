import Feather from '@expo/vector-icons/Feather';
import type { ComponentProps } from 'react';

export type IconName = ComponentProps<typeof Feather>['name'];

/**
 * Outline icons (Feather), drawn in the colour of the text beside them. They support a label and
 * never replace it, so they are hidden from screen readers.
 */
export function Icon({ name, size = 20, color }: { name: IconName; size?: number; color: string }) {
  return <Feather name={name} size={size} color={color} accessibilityElementsHidden importantForAccessibility="no" />;
}
