#!/usr/bin/env node
const fs = require('fs');
const { spawn } = require('child_process');
const { CONFIG, fileExists, jsonOut, parseArgs, writeState } = require('./payin_payout_config');

function findExecutable(candidates) {
  for (const candidate of candidates) {
    if (candidate.includes(':') || candidate.includes('\\') || candidate.includes('/')) {
      if (fileExists(candidate)) return candidate;
    } else {
      return candidate;
    }
  }
  return candidates[candidates.length - 1];
}

function loadSql(args) {
  if (args.file) return fs.readFileSync(args.file, 'utf8');
  if (args.sql) return args.sql;
  if (args._.length) return args._.join(' ');
  throw new Error('Missing --sql or --file');
}

function stripComments(sql) {
  return sql
    .replace(/^\s*--.*$/gm, '')
    .replace(/\/\*[\s\S]*?\*\//g, '');
}

function splitStatements(sql) {
  const statements = [];
  let current = '';
  let quote = null;
  let escaped = false;
  for (const char of stripComments(sql)) {
    if (escaped) {
      current += char;
      escaped = false;
      continue;
    }
    if (char === '\\' && quote) {
      current += char;
      escaped = true;
      continue;
    }
    if (quote) {
      current += char;
      if (char === quote) quote = null;
      continue;
    }
    if (char === '\'' || char === '"' || char === '`') {
      quote = char;
      current += char;
      continue;
    }
    if (char === ';') {
      if (current.trim()) statements.push(current.trim());
      current = '';
      continue;
    }
    current += char;
  }
  if (current.trim()) statements.push(current.trim());
  return statements;
}

function sqlKind(sql) {
  const stripped = stripComments(sql).trim();
  const first = (stripped.match(/^([a-z]+)/i) || ['', ''])[1].toUpperCase();
  return first || 'UNKNOWN';
}

function isReadOnly(kind) {
  return ['SELECT', 'SHOW', 'DESC', 'DESCRIBE', 'EXPLAIN', 'WITH'].includes(kind);
}

function ensureLimit(sql, kind, limit) {
  if (!['SELECT', 'WITH'].includes(kind)) return sql;
  if (/\blimit\s+\d+/i.test(sql)) return sql;
  const trimmed = sql.trim().replace(/;+\s*$/, '');
  return `${trimmed} LIMIT ${Number(limit) || 100};`;
}

function parseTsv(stdout) {
  const lines = stdout.split(/\r?\n/).filter((line) => line.length > 0);
  if (!lines.length) return { columns: [], rows: [] };
  const columns = lines[0].split('\t');
  const rows = lines.slice(1).map((line) => {
    const values = line.split('\t');
    const row = {};
    columns.forEach((column, idx) => {
      row[column] = values[idx] === undefined ? null : values[idx];
    });
    return row;
  });
  return { columns, rows };
}

function resolveTarget(args, kind) {
  const requested = args.target || args.datasource || args.ds || CONFIG.defaultTarget;
  const target = CONFIG.targets[requested];
  if (!target) {
    throw new Error(`Unknown datasource target "${requested}". Use master or slave_1.`);
  }
  if (!isReadOnly(kind) && requested !== 'master') {
    throw new Error('Writes must target master. Rerun with --allow-write --target master after confirming write intent.');
  }
  return { name: requested, config: target };
}

function runMysql(target, sql, timeoutMs) {
  return new Promise((resolve, reject) => {
    const exe = findExecutable(CONFIG.mysqlCandidates);
    const args = [
      '--batch',
      '--default-character-set=utf8mb4',
      `--host=${target.host}`,
      `--port=${target.port}`,
      `--user=${target.user}`,
      `--password=${target.password}`,
      target.database,
      '--execute',
      sql,
    ];
    const child = spawn(exe, args, { windowsHide: true });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => child.kill(), timeoutMs);
    child.stdout.on('data', (data) => { stdout += data.toString(); });
    child.stderr.on('data', (data) => { stderr += data.toString(); });
    child.on('error', reject);
    child.on('close', (code) => {
      clearTimeout(timer);
      const filteredStderr = stderr
        .split(/\r?\n/)
        .filter((line) => line && !/Using a password on the command line interface can be insecure/i.test(line))
        .join('\n');
      resolve({ code, stdout, stderr: filteredStderr, executable: exe });
    });
  });
}

async function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  try {
    const originalSql = loadSql(args);
    const statements = splitStatements(originalSql);
    if (statements.length !== 1) {
      throw new Error('Multiple SQL statements are not allowed; run one statement at a time.');
    }
    const kind = sqlKind(statements[0]);
    if (!isReadOnly(kind) && !args['allow-write']) {
      throw new Error(`Refusing ${kind} without --allow-write`);
    }
    const target = resolveTarget(args, kind);
    const sql = ensureLimit(statements[0], kind, args.limit || 100);
    const result = await runMysql(target.config, sql, Number(args['timeout-ms']) || 60000);
    const parsed = parseTsv(result.stdout);
    const ok = result.code === 0;
    const evidence = {
      env: CONFIG.env,
      target: target.name,
      host: target.config.host,
      port: target.config.port,
      database: target.config.database,
      user: target.config.user,
      sqlKind: kind,
      executable: result.executable,
      exitCode: result.code,
      rowCount: parsed.rows.length,
      stderr: result.stderr || undefined,
    };
    const stateFile = writeState({
      lastAction: {
        type: 'mysql_query',
        ok,
        evidence,
      },
    });
    jsonOut({
      ok,
      statePath: stateFile,
      evidence,
      columns: parsed.columns,
      rows: args.raw ? undefined : parsed.rows,
      raw: args.raw ? result.stdout : undefined,
    }, ok ? 0 : 1);
  } catch (e) {
    writeState({
      lastAction: {
        type: 'mysql_query',
        ok: false,
        evidence: { error: e.message },
      },
    });
    jsonOut({ ok: false, error: e.message }, 1);
  }
}

if (require.main === module) main();

module.exports = { main };
