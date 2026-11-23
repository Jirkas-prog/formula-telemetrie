'use strict';

const crypto = require('node:crypto');
const fsp = require('node:fs/promises');
const path = require('node:path');
const { ensureDir, readJson, writeJson } = require('./files');

const SESSION_LIFETIME_MS = 30 * 24 * 60 * 60 * 1000;

function normalizeUsername(value) {
  if (typeof value !== 'string') throw new Error('Uživatelské jméno chybí.');
  const username = value.trim();
  if (!/^[\p{L}\p{N}_.-]{3,32}$/u.test(username)) {
    throw new Error('Jméno musí mít 3–32 znaků a smí obsahovat písmena, čísla, tečku, pomlčku a podtržítko.');
  }
  return username;
}

function assertPassword(password) {
  if (typeof password !== 'string' || password.length < 8 || password.length > 200) {
    throw new Error('Heslo musí mít 8–200 znaků.');
  }
}

function hashPassword(password, salt = crypto.randomBytes(16)) {
  const result = crypto.scryptSync(password, salt, 64, { N: 16384, r: 8, p: 1 });
  return `scrypt$16384$8$1$${salt.toString('base64')}$${result.toString('base64')}`;
}

function verifyPassword(password, encoded) {
  try {
    const [algorithm, n, r, p, salt64, hash64] = encoded.split('$');
    if (algorithm !== 'scrypt') return false;
    const expected = Buffer.from(hash64, 'base64');
    const actual = crypto.scryptSync(password, Buffer.from(salt64, 'base64'), expected.length, {
      N: Number(n), r: Number(r), p: Number(p),
    });
    return crypto.timingSafeEqual(actual, expected);
  } catch {
    return false;
  }
}

class AuthStore {
  constructor(root) {
    this.root = root;
    this.usersFile = path.join(root, 'users.json');
    this.sessionsFile = path.join(root, 'sessions.json');
    this.recoveryFile = path.join(path.dirname(root), 'account-recovery.json');
  }

  async init() {
    await ensureDir(this.root, 0o700);
    const users = await readJson(this.usersFile, null);
    if (!users) await writeJson(this.usersFile, { version: 1, nextCompileUid: 20001, users: [] });
    const sessions = await readJson(this.sessionsFile, null);
    if (!sessions) await writeJson(this.sessionsFile, { version: 1, sessions: [] });
    await this.consumeRecovery();
  }

  async register(rawUsername, password) {
    const username = normalizeUsername(rawUsername);
    assertPassword(password);
    const store = await readJson(this.usersFile, { version: 1, nextCompileUid: 20001, users: [] });
    if (store.users.some((user) => user.username.toLocaleLowerCase('cs') === username.toLocaleLowerCase('cs'))) {
      throw new Error('Účet s tímto jménem už existuje.');
    }
    if (store.nextCompileUid > 60000) throw new Error('Byl dosažen limit lokálních účtů.');
    const user = {
      id: crypto.randomUUID(),
      username,
      passwordHash: hashPassword(password),
      compileUid: store.nextCompileUid++,
      createdAt: new Date().toISOString(),
    };
    store.users.push(user);
    await writeJson(this.usersFile, store);
    return this.publicUser(user);
  }

  async login(rawUsername, password) {
    const username = normalizeUsername(rawUsername);
    const store = await readJson(this.usersFile, { users: [] });
    const user = store.users.find((item) => item.username.toLocaleLowerCase('cs') === username.toLocaleLowerCase('cs'));
    if (!user || !verifyPassword(password, user.passwordHash)) throw new Error('Nesprávné jméno nebo heslo.');
    return this.createSession(user);
  }

  async createSession(user) {
    const token = crypto.randomBytes(32).toString('base64url');
    const tokenHash = crypto.createHash('sha256').update(token).digest('hex');
    const store = await readJson(this.sessionsFile, { version: 1, sessions: [] });
    const now = Date.now();
    store.sessions = store.sessions.filter((session) => Date.parse(session.expiresAt) > now);
    store.sessions.push({
      tokenHash,
      userId: user.id,
      expiresAt: new Date(now + SESSION_LIFETIME_MS).toISOString(),
    });
    await writeJson(this.sessionsFile, store);
    return { token, user: this.publicUser(user) };
  }

  async session(token) {
    if (!token) return null;
    const tokenHash = crypto.createHash('sha256').update(token).digest('hex');
    const sessions = await readJson(this.sessionsFile, { sessions: [] });
    const session = sessions.sessions.find((item) => item.tokenHash === tokenHash && Date.parse(item.expiresAt) > Date.now());
    if (!session) return null;
    const users = await readJson(this.usersFile, { users: [] });
    const user = users.users.find((item) => item.id === session.userId);
    return user ? this.publicUser(user) : null;
  }

  async logout(token) {
    if (!token) return;
    const tokenHash = crypto.createHash('sha256').update(token).digest('hex');
    const store = await readJson(this.sessionsFile, { version: 1, sessions: [] });
    store.sessions = store.sessions.filter((session) => session.tokenHash !== tokenHash);
    await writeJson(this.sessionsFile, store);
  }

  async consumeRecovery() {
    let request;
    try {
      request = JSON.parse(await fsp.readFile(this.recoveryFile, 'utf8'));
    } catch (error) {
      if (error.code === 'ENOENT') return false;
      throw error;
    }
    if (!request || typeof request.username !== 'string' || typeof request.new_password !== 'string') return false;
    const username = normalizeUsername(request.username);
    assertPassword(request.new_password);
    const store = await readJson(this.usersFile, { users: [] });
    const user = store.users.find((item) => item.username.toLocaleLowerCase('cs') === username.toLocaleLowerCase('cs'));
    if (!user) throw new Error(`Obnova hesla: účet ${username} neexistuje.`);
    user.passwordHash = hashPassword(request.new_password);
    user.passwordResetAt = new Date().toISOString();
    await writeJson(this.usersFile, store);
    await writeJson(this.recoveryFile, {
      processed: true,
      username,
      processedAt: user.passwordResetAt,
      note: 'Heslo bylo zahashováno; plaintext byl odstraněn.',
    });
    return true;
  }

  publicUser(user) {
    return { id: user.id, username: user.username, compileUid: user.compileUid };
  }
}

module.exports = { AuthStore, hashPassword, normalizeUsername, verifyPassword };

