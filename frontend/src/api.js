/**
 * api.js — Thin client for the Spring Boot backend (port 8080).
 *
 * Token storage: JWT is kept in sessionStorage under "sahayak_token".
 * All authenticated calls automatically attach the Bearer header.
 */

const BASE = import.meta.env.VITE_API_BASE_URL
  ? `${import.meta.env.VITE_API_BASE_URL}/api`
  : "http://localhost:8080/api";

// ─── Token helpers ────────────────────────────────────────────────────────────

export function getToken() {
  return sessionStorage.getItem("sahayak_token");
}

export function saveToken(token) {
  sessionStorage.setItem("sahayak_token", token);
}

export function clearToken() {
  sessionStorage.removeItem("sahayak_token");
}

export function isLoggedIn() {
  return !!getToken();
}

// ─── Low-level fetch wrappers ─────────────────────────────────────────────────

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function _request(method, path, body, requireAuth = false) {
  const headers = {
    "Content-Type": "application/json",
    ...(requireAuth ? authHeaders() : {}),
  };

  const opts = { method, headers };
  if (body !== undefined) opts.body = JSON.stringify(body);

  const res = await fetch(BASE + path, opts);

  if (res.status === 401) {
    clearToken();
    throw new Error("Session expired. Please log in again.");
  }

  if (!res.ok) {
    let msg = "";
    try {
      const raw = await res.text();
      try {
        const err = JSON.parse(raw);
        msg = err.message || err.error || raw;
      } catch {
        msg = raw;
      }
    } catch (_) {}
    if (!msg || msg.trim() === "") {
      msg = `API ${method} ${path} → ${res.status}`;
    }
    throw new Error(msg);
  }

  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

const _get  = (path, auth = false) => _request("GET",  path, undefined, auth);
const _post = (path, body, auth = false) => _request("POST", path, body, auth);
const _put  = (path, body, auth = false) => _request("PUT",  path, body, auth);

// ─── Auth ─────────────────────────────────────────────────────────────────────

/**
 * Register a new user.
 * @param {{ name, email, password, state }} data
 * @returns {Promise<string>}  server success message
 */
export async function register(data) {
  return _post("/auth/register", data);
}

/**
 * Login and persist the JWT.
 * @param {{ email, password }} data
 * @returns {Promise<{ token: string, email: string, name: string }>}
 */
export async function login(data) {
  const res = await _post("/auth/login", data);
  if (res?.token) saveToken(res.token);
  return res;
}

/** Clear stored JWT (client-side logout). */
export function logout() {
  clearToken();
}

/**
 * Fetch logged-in user info.
 * @returns {Promise<{ email, name, state }>}
 */
export async function getMe() {
  return _get("/auth/me", true);
}

// ─── Profile (socioeconomic details) ─────────────────────────────────────────

/**
 * Create or update the user's socioeconomic profile.
 * @param {object} profileData  matches ProfileRequest DTO on the backend
 */
export async function saveProfile(profileData) {
  // Backend handles upsert on both POST and PUT
  try {
    return await _post("/profile", profileData, true);
  } catch (err) {
    if (err.message?.toLowerCase().includes("already exists")) {
      return await _put("/profile", profileData, true);
    }
    throw err;
  }
}

/**
 * Fetch the logged-in user's socioeconomic profile.
 */
export async function getProfile() {
  return _get("/profile", true);
}

// ─── Schemes — public endpoints ───────────────────────────────────────────────

/**
 * Fetch all schemes from the database.
 * @returns {Promise<Array>}
 */
export async function fetchAllSchemes() {
  return _get("/schemes");
}

/**
 * Semantic (vector) search via the ML FastAPI service.
 * Spring Boot proxies: GET /api/schemes/semantic-search?q=...&topK=...&language=...
 *
 * Returns { results: [{name, category, state, snippet, relevance_score}], returned, elapsed_ms }
 */
export async function semanticSearch(query, topK = 10, language = "en") {
  const params = new URLSearchParams({ q: query, topK, language });
  return _get(`/schemes/semantic-search?${params}`);
}

/**
 * Plain keyword search (Spring Data JPA — fast, no ML needed).
 */
export async function keywordSearch(query) {
  return _get(`/schemes/search?q=${encodeURIComponent(query)}`);
}

// ─── Schemes — authenticated endpoints ───────────────────────────────────────

/**
 * Get schemes personalised for the logged-in user's profile.
 * Calls Spring Boot → POST /match on FastAPI → XGBoost scored results.
 *
 * @param {number} topN      Max schemes to return (default 20)
 * @param {string} minStatus Minimum eligibility status: LIKELY_ELIGIBLE | ELIGIBLE
 * @returns {Promise<{ results: Array<MatchedScheme>, returned, total_schemes, elapsed_ms }>}
 */
export async function getMySchemes(topN = 20, minStatus = "LIKELY_ELIGIBLE") {
  const params = new URLSearchParams({ topN, minStatus });
  return _get(`/schemes/my?${params}`, true);
}

// ─── Saved schemes ──────────────────────────────────────────────────────────────

/** Fetch all saved scheme IDs for the logged-in user. */
export async function fetchSavedSchemes() {
  return _get("/saved", true);
}

/** Save a scheme by ID (requires JWT). */
export async function saveScheme(schemeId) {
  return _request("POST", `/saved/${schemeId}`, undefined, true);
}

/** Remove a saved scheme by ID (requires JWT). */
export async function unsaveScheme(schemeId) {
  return _request("DELETE", `/saved/${schemeId}`, undefined, true);
}
