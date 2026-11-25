import { ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useAuth } from '@/auth/AuthProvider';
import { Button } from '@/design-system/components';
import { displayFont, layout, radius, space, type, useTheme } from '@/design-system/tokens';

import { MfaCard } from './MfaCard';

/**
 * Shown instead of the app when the clinic requires two-step sign-in for this person's role and they
 * have not set it up. The server refuses everything else until they do, so this is the only useful
 * screen; once it is on, the app starts normally.
 */
export function MfaRequiredScreen() {
  const t = useTheme();
  const { me, retryBoot, signOut } = useAuth();
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.background }}>
      <ScrollView automaticallyAdjustKeyboardInsets keyboardShouldPersistTaps="handled" contentContainerStyle={{ flexGrow: 1, justifyContent: 'center', padding: space.lg }}>
        <View style={{ width: '100%', maxWidth: layout.form + 80, alignSelf: 'center', gap: space.lg }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
            <View style={{ width: 44, height: 44, borderRadius: radius.md, backgroundColor: t.hero, alignItems: 'center', justifyContent: 'center' }}>
              <Text style={{ color: t.heroText, fontSize: 24, fontWeight: '700', fontFamily: displayFont }}>A</Text>
            </View>
            <Text style={{ color: t.text, fontSize: 22, fontWeight: '700', fontFamily: displayFont }}>AarogyaOS</Text>
          </View>
          <View style={{ gap: space.xs }}>
            <Text accessibilityRole="header" style={[type.display, { color: t.text }]}>Set up two-step sign-in</Text>
            <Text style={[type.body, { color: t.textMuted }]}>
              Your clinic requires it for your role. You will need an authenticator app on your phone. Once it is on, the app opens as usual.
            </Text>
          </View>
          <MfaCard required onEnabled={retryBoot} />
          <Text style={[type.small, { color: t.textMuted }]}>Signed in as {me?.email}.</Text>
          <Button title="Sign out" variant="ghost" onPress={() => void signOut()} />
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
