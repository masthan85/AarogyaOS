import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react-native';

import { MfaRequiredScreen } from '../MfaRequiredScreen';

const mockSignOut = jest.fn();
const mockStart = jest.fn();
jest.mock('@/auth/AuthProvider', () => ({
  useAuth: () => ({ me: { email: 'doctor@demo.example.com' }, retryBoot: jest.fn(), signOut: mockSignOut }),
}));
jest.mock('@/api/endpoints', () => ({
  getMfaStatus: () => Promise.resolve({ enabled: false, recovery_codes_remaining: 0 }),
  startMfaEnrolment: () => mockStart(),
  confirmMfa: jest.fn(),
  disableMfa: jest.fn(),
}));
jest.mock('react-native-safe-area-context', () => require('react-native-safe-area-context/jest/mock').default);
jest.mock('react-native-qrcode-svg', () => {
  const { Text } = require('react-native');
  return function QRCode({ value }: { value: string }) {
    return <Text testID="qr">{value}</Text>;
  };
});

let client: QueryClient;
beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
});
afterEach(() => client.clear());

const wrap = () => (
  <QueryClientProvider client={client}>
    <MfaRequiredScreen />
  </QueryClientProvider>
);

describe('required two-step sign-in', () => {
  it('explains why, offers set-up with a QR code, and still lets the person sign out', async () => {
    mockStart.mockResolvedValueOnce({ secret: 'JBSWY3DPEHPK3PXP', otpauth_uri: 'otpauth://totp/AarogyaOS:doctor?secret=JBSWY3DPEHPK3PXP' });
    await render(wrap());
    expect(screen.getByText(/Your clinic requires it for your role/)).toBeTruthy();
    expect(screen.getByText('Signed in as doctor@demo.example.com.')).toBeTruthy();

    await fireEvent.press(await screen.findByRole('button', { name: 'Set up' }));
    expect(await screen.findByTestId('qr')).toBeTruthy();
    expect(screen.getByText('JBSW Y3DP EHPK 3PXP')).toBeTruthy();
    // No way to switch it off is offered when the clinic requires it.
    expect(screen.queryByRole('button', { name: 'Turn off' })).toBeNull();

    await fireEvent.press(screen.getByRole('button', { name: 'Sign out' }));
    expect(mockSignOut).toHaveBeenCalledTimes(1);
  });
});
