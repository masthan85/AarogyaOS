jest.mock('expo-clipboard', () => ({ getStringAsync: jest.fn(), setStringAsync: jest.fn() }));

import { copyThenClear } from '../clipboard';

function fakeBoard(initial = '') {
  let value = initial;
  return { board: { read: async () => value, write: async (t: string) => { value = t; } }, get: () => value, set: (v: string) => { value = v; } };
}

describe('copyThenClear', () => {
  it('copies, then clears when the clipboard still holds our text', async () => {
    const f = fakeBoard();
    let fire: () => void = () => undefined;
    await copyThenClear('visit text', f.board, 1000, (fn) => { fire = fn; });
    expect(f.get()).toBe('visit text');
    fire();
    await new Promise((r) => setImmediate(r));
    expect(f.get()).toBe('');
  });

  it('leaves something the person copied in the meantime alone', async () => {
    const f = fakeBoard();
    let fire: () => void = () => undefined;
    await copyThenClear('visit text', f.board, 1000, (fn) => { fire = fn; });
    f.set('something else');
    fire();
    await new Promise((r) => setImmediate(r));
    expect(f.get()).toBe('something else');
  });
});
