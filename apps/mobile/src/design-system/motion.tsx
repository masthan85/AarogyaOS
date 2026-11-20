import type { ReactNode } from 'react';
import type { ViewStyle } from 'react-native';
import Animated, { FadeInDown, ReduceMotion } from 'react-native-reanimated';

/**
 * Motion is used once per screen: sections settle into place when a screen first opens, a short
 * step apart, so the eye reads them in order. Nothing moves on its own after that. When the device
 * asks for reduced motion the sections simply appear.
 */
export const MOTION = { duration: 260, step: 45, rise: 10 } as const;

export function Reveal({ index = 0, children, style }: { index?: number; children: ReactNode; style?: ViewStyle }) {
  return (
    <Animated.View
      style={style}
      entering={FadeInDown.duration(MOTION.duration)
        .delay(index * MOTION.step)
        .withInitialValues({ opacity: 0, transform: [{ translateY: MOTION.rise }] })
        .reduceMotion(ReduceMotion.System)}>
      {children}
    </Animated.View>
  );
}
