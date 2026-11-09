/**
 * Every field the app's zod schemas require must exist in the API's response for that endpoint.
 * `contract.json` is generated from the API's OpenAPI document (services/api/scripts/export_contract.py)
 * and a backend test keeps it current, so a renamed or removed field fails here instead of on a phone.
 */
import fs from 'fs';
import path from 'path';
import { z } from 'zod';

import contract from '../contract.json';
import * as schemas from '../schemas';

const source = fs.readFileSync(path.join(__dirname, '..', 'endpoints.ts'), 'utf8');
const fields = contract as Record<string, string[]>;

type Call = { method: string; path: string; schemaName: string };

function calls(): Call[] {
  const out: Call[] = [];
  const re = /api\.request\(\s*[`'"]([^`'"]+)[`'"]\s*,\s*(z\.array\(\s*)?(\w+)([\s\S]*?)\)\s*(?:;|\n\S)/g;
  for (const m of source.matchAll(re)) {
    const rest = m[4] ?? '';
    const method = /method:\s*'(\w+)'/.exec(rest)?.[1] ?? 'GET';
    const p = m[1].split('?')[0].replace(/\$\{[^}]+\}/g, '{}');
    out.push({ method, path: p, schemaName: m[3] });
  }
  return out;
}

function lookup(method: string, p: string): string[] | undefined {
  // Contract paths use named parameters ({invoice_id}); calls use {} for every ${...}.
  const want = p.split('/').map((s) => (s === '{}' ? '{}' : s));
  for (const [key, value] of Object.entries(fields)) {
    const [m, kp] = [key.split(' ')[0], key.slice(key.indexOf(' ') + 1)];
    if (m !== method) continue;
    const parts = kp.split('/');
    if (parts.length !== want.length) continue;
    if (parts.every((s, i) => (s.startsWith('{') && want[i] === '{}') || s === want[i])) return value;
  }
  return undefined;
}

describe('API contract', () => {
  const all = calls();

  it('finds the calls it is meant to check', () => {
    expect(all.length).toBeGreaterThan(60);
  });

  it.each(all.map((c) => [`${c.method} ${c.path} -> ${c.schemaName}`, c] as const))('%s', (_label, c) => {
    const schema = (schemas as Record<string, unknown>)[c.schemaName];
    if (!(schema instanceof z.ZodObject)) return; // inline or non-object schemas are not checked
    const response = lookup(c.method, c.path);
    if (!response) return; // endpoint returns no JSON object (for example a file)
    const missing = Object.keys(schema.shape).filter((k) => !response.includes(k));
    expect(missing).toEqual([]);
  });
});
