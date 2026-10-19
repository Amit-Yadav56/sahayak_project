import React, { useState } from "react";
import { register, login } from "../api.js";

/**
 * AuthModal — login / register dialog
 * Props:
 *   onSuccess(userData)  called after successful auth with { email, name }
 *   onClose()
 */
export default function AuthModal({ onSuccess, onClose }) {
  const [mode, setMode] = useState("login"); // "login" | "register"
  const [form, setForm] = useState({ name: "", email: "", password: "", state: "" });
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const STATES = [
    "Andhra Pradesh","Arunachal Pradesh","Assam","Bihar","Chhattisgarh",
    "Goa","Gujarat","Haryana","Himachal Pradesh","Jharkhand","Karnataka",
    "Kerala","Madhya Pradesh","Maharashtra","Manipur","Meghalaya","Mizoram",
    "Nagaland","Odisha","Punjab","Rajasthan","Sikkim","Tamil Nadu","Telangana",
    "Tripura","Uttar Pradesh","Uttarakhand","West Bengal",
    "Delhi","Jammu & Kashmir","Ladakh","Chandigarh","Puducherry",
  ];

  const set = (k) => (e) => setForm((p) => ({ ...p, [k]: e.target.value }));

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (mode === "register") {
        await register({ name: form.name, email: form.email, password: form.password, state: form.state });
        // Auto-login after register
      }
      const res = await login({ email: form.email, password: form.password });
      onSuccess(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" style={{ maxWidth: 420 }} onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>✕</button>

        <h2 style={{ fontSize: "1.3rem", marginBottom: "4px" }}>
          {mode === "login" ? "Sign In to Sahayak" : "Create Account"}
        </h2>
        <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", marginBottom: "20px" }}>
          {mode === "login"
            ? "Sign in to get personalised scheme recommendations."
            : "Create an account to unlock ML-powered eligibility matching."}
        </p>

        {error && (
          <div style={{
            background: "#fee2e2", border: "1px solid #fca5a5",
            borderRadius: 6, padding: "10px 14px",
            color: "#b91c1c", fontSize: "0.85rem", marginBottom: 16
          }}>
            <div>{error}</div>
            {error.toLowerCase().includes("already exists") && (
              <div style={{ marginTop: 6 }}>
                <button
                  type="button"
                  style={{
                    background: "none", border: "none", color: "#1d4ed8",
                    textDecoration: "underline", fontWeight: 700, cursor: "pointer", padding: 0
                  }}
                  onClick={() => { setMode("login"); setError(null); }}
                >
                  This email is already registered. Click here to Sign In →
                </button>
              </div>
            )}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {mode === "register" && (
            <>
              <div className="form-group">
                <label className="form-label">Full Name</label>
                <input className="form-control" type="text" required
                  placeholder="Ramesh Kumar" value={form.name} onChange={set("name")} />
              </div>
              <div className="form-group">
                <label className="form-label">State</label>
                <select className="form-control" required value={form.state} onChange={set("state")}>
                  <option value="">— Select your state —</option>
                  {STATES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
            </>
          )}

          <div className="form-group">
            <label className="form-label">Email</label>
            <input className="form-control" type="email" required
              placeholder="you@example.com" value={form.email} onChange={set("email")} />
          </div>

          <div className="form-group">
            <label className="form-label">Password</label>
            <input className="form-control" type="password" required
              placeholder="••••••••" value={form.password} onChange={set("password")} />
          </div>

          <button
            type="submit"
            className="btn-sm btn-primary"
            disabled={loading}
            style={{ width: "100%", padding: "12px", marginTop: 8, fontSize: "1rem" }}
          >
            {loading ? "Please wait…" : mode === "login" ? "Sign In" : "Create Account & Sign In"}
          </button>
        </form>

        <p style={{ textAlign: "center", marginTop: 16, fontSize: "0.85rem", color: "var(--text-muted)" }}>
          {mode === "login" ? "Don't have an account? " : "Already registered? "}
          <button
            type="button"
            style={{ background: "none", border: "none", color: "var(--primary)", cursor: "pointer", fontWeight: 600 }}
            onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}
          >
            {mode === "login" ? "Register" : "Sign In"}
          </button>
        </p>
      </div>
    </div>
  );
}
