/**
 * A key that names one intended action, sent as `Idempotency-Key`. The server does the action once
 * per key, so a request repeated after a lost reply cannot, for example, record a payment twice.
 * Keep the same key while retrying the same action; take a new one for the next action.
 */
export function newRequestKey(): string {
  const random = () => Math.random().toString(36).slice(2, 12).padEnd(10, '0');
  return `${Date.now().toString(36)}-${random()}${random()}`;
}
