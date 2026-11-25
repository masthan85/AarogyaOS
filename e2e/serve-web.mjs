// Serves the static web export (`npx expo export -p web`) the way expo-router expects, for the
// browser tests: /billing/123 is answered by billing/[id].html, unknown paths by +not-found.html.
// Development aid only; production hosting is described in docs/11-DEPLOYMENT-GUIDE.md.
// Usage: node serve-web.mjs <export dir> [port]
import { createServer } from 'node:http';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { extname, join, normalize, resolve } from 'node:path';

const root = resolve(process.argv[2] ?? 'dist');
const port = Number(process.argv[3] ?? 8081);
const types = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.ttf': 'font/ttf', '.woff2': 'font/woff2',
};

const isFile = (p) => existsSync(p) && statSync(p).isFile();

/** Walks the export like the router: exact names first, then [param] files and folders, skipping (group) folders. */
function route(dir, parts) {
  if (parts.length === 0) return isFile(join(dir, 'index.html')) ? join(dir, 'index.html') : undefined;
  const [head, ...rest] = parts;
  const entries = readdirSync(dir, { withFileTypes: true });
  if (rest.length === 0 && isFile(join(dir, `${head}.html`))) return join(dir, `${head}.html`);
  if (entries.some((e) => e.isDirectory() && e.name === head)) {
    const found = route(join(dir, head), rest);
    if (found) return found;
  }
  for (const e of entries.filter((e) => e.isDirectory() && /^\(.+\)$/.test(e.name))) {
    const found = route(join(dir, e.name), parts);
    if (found) return found;
  }
  for (const e of entries.filter((e) => /^\[[^.\]]+\]/.test(e.name))) {
    if (rest.length === 0 && e.isFile() && e.name.endsWith('.html')) return join(dir, e.name);
    if (e.isDirectory()) {
      const found = route(join(dir, e.name), rest);
      if (found) return found;
    }
  }
  return undefined;
}

createServer((req, res) => {
  const path = decodeURIComponent(new URL(req.url ?? '/', 'http://x').pathname);
  const asset = normalize(join(root, path));
  if (!asset.startsWith(root)) { res.writeHead(400).end(); return; }
  let file = isFile(asset) ? asset : route(root, path.split('/').filter(Boolean));
  let status = 200;
  if (!file) { file = join(root, '+not-found.html'); status = 404; }
  res.writeHead(status, { 'Content-Type': types[extname(file)] ?? 'application/octet-stream' });
  res.end(readFileSync(file));
}).listen(port, () => console.log(`Serving ${root} on http://localhost:${port}`));
