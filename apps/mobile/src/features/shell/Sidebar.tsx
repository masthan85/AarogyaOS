import { useQuery } from '@tanstack/react-query';
import { type Href, router, usePathname } from 'expo-router';
import { Pressable, ScrollView, Text, View } from 'react-native';

import { getOrganisation } from '@/api/endpoints';
import { useAuth } from '@/auth/AuthProvider';
import { Avatar } from '@/design-system/components';
import { Icon, type IconName } from '@/design-system/icons';
import { displayFont, layout, MIN_TOUCH_SMALL, radius, space, type, useTheme } from '@/design-system/tokens';
import { can, roleLabel } from '@/domain/permissions';
import { arrange, DASHBOARD_ACTIONS } from '@/features/dashboard/actions';

/** Moves to a top-level section without piling screens on top of each other. */
function open(href: Href) {
  if (router.canDismiss()) router.dismissAll();
  if (href !== '/') router.push(href);
}

function Item({ icon, label, active, onPress }: { icon: IconName; label: string; active?: boolean; onPress: () => void }) {
  const t = useTheme();
  return (
    <Pressable
      accessibilityRole="link"
      accessibilityState={{ selected: !!active }}
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed, hovered }: { pressed: boolean; hovered?: boolean }) => ({
        minHeight: MIN_TOUCH_SMALL,
        flexDirection: 'row',
        alignItems: 'center',
        gap: 12,
        paddingHorizontal: 12,
        borderRadius: radius.md,
        backgroundColor: active ? t.primarySoft : hovered || pressed ? t.neutralSoft : 'transparent',
      })}>
      <Icon name={icon} size={18} color={active ? t.primary : t.textMuted} />
      <Text style={{ fontSize: 15, fontWeight: active ? '700' : '500', color: active ? t.primary : t.text }}>{label}</Text>
    </Pressable>
  );
}

/** Navigation for wide screens. Phones and narrow tablets use the home screen's tiles instead. */
export function Sidebar() {
  const t = useTheme();
  const { me, signOut } = useAuth();
  const path = usePathname();
  const org = useQuery({ queryKey: ['organisation'], queryFn: getOrganisation, enabled: can(me, 'org:read') });
  if (!me) return null;
  const groups = arrange(DASHBOARD_ACTIONS, (p) => can(me, p));
  const isActive = (href?: Href) => typeof href === 'string' && (path === href || path.startsWith(`${href}/`));

  return (
    <View
      accessibilityRole="navigation"
      style={{ width: layout.sidebar, backgroundColor: t.surface, borderRightWidth: 1, borderRightColor: t.border }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, padding: space.md, paddingTop: space.lg }}>
        <View style={{ width: 36, height: 36, borderRadius: 10, backgroundColor: t.hero, alignItems: 'center', justifyContent: 'center' }}>
          <Text style={{ color: t.heroText, fontSize: 20, fontWeight: '700', fontFamily: displayFont }}>A</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: t.text, fontSize: 18, fontWeight: '700', fontFamily: displayFont }}>AarogyaOS</Text>
          {org.data?.name ? (
            <Text numberOfLines={1} style={[type.caption, { color: t.textMuted, fontWeight: '500' }]}>{org.data.name}</Text>
          ) : null}
        </View>
      </View>

      <ScrollView contentContainerStyle={{ paddingHorizontal: 12, paddingBottom: space.md, gap: space.md }}>
        <Item icon="grid" label="Home" active={path === '/'} onPress={() => open('/')} />
        {groups.map((g) => (
          <View key={g.group} style={{ gap: 2 }}>
            <Text style={[type.caption, { color: t.textMuted, paddingHorizontal: 12, paddingBottom: 4 }]}>{g.title}</Text>
            {g.actions.map((a) => (
              <Item key={a.key} icon={a.icon} label={a.title} active={isActive(a.href)} onPress={() => a.href && open(a.href)} />
            ))}
          </View>
        ))}
      </ScrollView>

      <View style={{ borderTopWidth: 1, borderTopColor: t.border, padding: 12, gap: 2 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 4, paddingVertical: space.sm }}>
          <Avatar name={me.full_name} size={36} />
          <View style={{ flex: 1 }}>
            <Text numberOfLines={1} style={{ color: t.text, fontSize: 14, fontWeight: '700' }}>{me.full_name}</Text>
            <Text numberOfLines={1} style={{ color: t.textMuted, fontSize: 12.5 }}>{me.roles.map(roleLabel).join(', ')}</Text>
          </View>
        </View>
        <Item icon="settings" label="Settings" active={isActive('/settings')} onPress={() => open('/settings')} />
        <Item icon="log-out" label="Sign out" onPress={() => void signOut()} />
      </View>
    </View>
  );
}
