// Starts the FinAlly backend for a local E2E run (used by playwright.config.ts webServer).
// Fresh throwaway DB every run, deterministic mock LLM, seeded simulator, static frontend export.
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const staticDir = process.env.STATIC_DIR ?? path.join(repo, 'frontend', 'out');
const dbPath = process.env.E2E_DB_PATH ?? path.join(os.tmpdir(), 'finally-e2e', 'finally-e2e.db');
const port = process.env.E2E_PORT ?? '8003';

if (!existsSync(path.join(staticDir, 'index.html'))) {
  console.error(`[start-server] No frontend build at ${staticDir}. Run "npm run build:frontend" first.`);
  process.exit(1);
}

// Delete the previous run's DB (and SQLite side files) so every run starts from the seed.
for (const suffix of ['', '-wal', '-shm', '-journal']) rmSync(dbPath + suffix, { force: true });
mkdirSync(path.dirname(dbPath), { recursive: true });
console.log(`[start-server] DB_PATH=${dbPath} STATIC_DIR=${staticDir} port=${port}`);

const venvPython = path.join(repo, 'backend', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const command = existsSync(venvPython) ? venvPython : 'uv';
const args = existsSync(venvPython)
  ? ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', port]
  : ['run', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', port];
const child = spawn(command, args, {
  cwd: path.join(repo, 'backend'),
  stdio: 'inherit',
  env: {
    ...process.env,
    LLM_MOCK: 'true',
    SIM_SEED: '42',
    DB_PATH: dbPath,
    STATIC_DIR: staticDir,
    // Empty values win over <repo>/.env (python-dotenv never overrides set variables),
    // so a developer's real keys can't switch the run to Massive or OpenRouter.
    MASSIVE_API_KEY: '',
    OPENROUTER_API_KEY: '',
    // Live-talk sections (planning/charla/CONTRACT.md §10). charla_only stays false so the FinAlly specs still run.
    CHARLA_ADMIN_KEY: 'e2e',
    CHARLA_DEV_LINKS: 'true',
    CHARLA_PHONE_AT: 'off',
    RESEND_API_KEY: '',
    CHARLA_ONLY: 'false',
    CHARLA_PUBLIC_URL: '',
  },
});

const stop = () => child.kill();
process.on('SIGINT', stop);
process.on('SIGTERM', stop);
child.on('exit', (code, signal) => process.exit(code ?? (signal ? 1 : 0)));
