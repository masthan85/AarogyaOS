import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import { ApiError } from '@/api/client';

import { LoginScreen } from '../LoginScreen';

const mockSignIn = jest.fn();
jest.mock('@/auth/AuthProvider', () => ({ useAuth: () => ({ signIn: mockSignIn }) }));
jest.mock('react-native-safe-area-context', () => require('react-native-safe-area-context/jest/mock').default);

beforeEach(() => mockSignIn.mockReset());

describe('sign-in screen', () => {
  it('says what is missing instead of sending an empty form', async () => {
    await render(<LoginScreen />);
    await fireEvent.press(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('Enter your email address')).toBeTruthy();
    expect(screen.getByText('Enter your password')).toBeTruthy();
    expect(mockSignIn).not.toHaveBeenCalled();
  });

  it('sends the organisation, email and password and reports wrong details plainly', async () => {
    mockSignIn.mockRejectedValueOnce(new ApiError(401, 'Unauthorized'));
    await render(<LoginScreen />);
    await fireEvent.changeText(screen.getByLabelText('Organisation'), 'Demo-Clinic');
    await fireEvent.changeText(screen.getByLabelText('Email'), 'doctor@demo.example.com');
    await fireEvent.changeText(screen.getByLabelText('Password'), 'secret-password');
    await fireEvent.press(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => expect(mockSignIn).toHaveBeenCalledTimes(1));
    expect(mockSignIn.mock.calls[0][0]).toMatchObject({ organisationSlug: 'demo-clinic', email: 'doctor@demo.example.com', password: 'secret-password' });
    expect(await screen.findByText('Email, password or organisation is incorrect.')).toBeTruthy();
  });

  it('asks for the second-step code when the account has one', async () => {
    mockSignIn.mockRejectedValueOnce(new ApiError(401, 'Enter the code', undefined, { title: 'mfa_required' }));
    await render(<LoginScreen />);
    await fireEvent.changeText(screen.getByLabelText('Email'), 'doctor@demo.example.com');
    await fireEvent.changeText(screen.getByLabelText('Password'), 'secret-password');
    await fireEvent.press(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByLabelText('Verification code')).toBeTruthy();
  });
});
