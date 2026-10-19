import React, { useState, useEffect } from "react";
import { getProfile, saveProfile } from "../api.js";

/**
 * ProfileForm — collects the user's socioeconomic details and saves them
 * to the backend (POST/PUT /api/profile). On save, calls onProfileSaved()
 * so the parent can re-fetch personalised schemes.
 */
export default function ProfileForm({ onProfileSaved }) {
  const [form, setForm] = useState({
    age: "",
    gender: "male",
    state: "",
    casteCategory: "General",
    annualIncome: "",
    incomeSource: "other",
    landAcres: "0",
    hasHouse: false,
    isWidow: false,
    disabilityType: "",
    childrenCount: "0",
    educationLevel: "none",
    hasBankAccount: true,
    hasAadhar: true,
  });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState(null);

  // Pre-fill from existing profile
  useEffect(() => {
    setLoading(true);
    getProfile()
      .then((p) => {
        if (p) {
          setForm({
            age: p.age ?? "",
            gender: p.gender ?? "male",
            state: p.state || (p.user ? p.user.state : "") || "",
            casteCategory: p.casteCategory ?? "General",
            annualIncome: p.annualIncome ?? "",
            incomeSource: p.incomeSource ?? "other",
            landAcres: p.landAcres ?? "0",
            hasHouse: p.hasHouse ?? false,
            isWidow: p.isWidow ?? false,
            disabilityType: p.disabilityType ?? "",
            childrenCount: p.childrenCount ?? "0",
            educationLevel: p.educationLevel ?? "none",
            hasBankAccount: p.hasBankAccount ?? true,
            hasAadhar: p.hasAadhar ?? true,
          });
        }
      })
      .catch(() => {/* no profile yet — blank form is fine */})
      .finally(() => setLoading(false));
  }, []);

  const set = (k) => (e) => {
    const val = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    setForm((p) => ({ ...p, [k]: val }));
  };

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await saveProfile({
        ...form,
        state: form.state,
        age: Number(form.age),
        annualIncome: Number(form.annualIncome),
        landAcres: Number(form.landAcres),
        childrenCount: Number(form.childrenCount),
      });
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
      onProfileSaved?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 40, color: "var(--text-muted)" }}>
        Loading your profile…
      </div>
    );
  }

  return (
    <div className="checker-box">
      <div className="checker-header">
        <h2 className="checker-title">Your Socioeconomic Profile</h2>
        <p className="checker-subtitle">
          Fill in your details accurately — the ML model uses these to score and rank which
          government schemes you are most likely eligible for.
        </p>
      </div>

      {error && (
        <div style={{
          background: "#fee2e2", border: "1px solid #fca5a5",
          borderRadius: 6, padding: "10px 14px",
          color: "#b91c1c", fontSize: "0.85rem", marginBottom: 16
        }}>
          {error}
        </div>
      )}

      {success && (
        <div style={{
          background: "#dcfce7", border: "1px solid #86efac",
          borderRadius: 6, padding: "10px 14px",
          color: "#166534", fontSize: "0.85rem", marginBottom: 16
        }}>
          ✓ Profile saved! Refreshing your personalised scheme matches…
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="checker-form">

          {/* ── Personal ─────────────────────────────── */}
          <div className="form-group">
            <label className="form-label">Age</label>
            <input type="number" className="form-control" min={1} max={120}
              required value={form.age} onChange={set("age")} placeholder="e.g. 35" />
          </div>

          <div className="form-group">
            <label className="form-label">Gender</label>
            <select className="form-control" value={form.gender} onChange={set("gender")}>
              <option value="male">Male</option>
              <option value="female">Female</option>
              <option value="other">Other / Prefer not to say</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">State of Residence</label>
            <select className="form-control" required value={form.state} onChange={set("state")}>
              <option value="">— Select your state —</option>
              {[
                "Andhra Pradesh","Arunachal Pradesh","Assam","Bihar","Chhattisgarh",
                "Goa","Gujarat","Haryana","Himachal Pradesh","Jharkhand","Karnataka",
                "Kerala","Madhya Pradesh","Maharashtra","Manipur","Meghalaya","Mizoram",
                "Nagaland","Odisha","Punjab","Rajasthan","Sikkim","Tamil Nadu","Telangana",
                "Tripura","Uttar Pradesh","Uttarakhand","West Bengal",
                "Delhi","Jammu & Kashmir","Ladakh","Chandigarh","Puducherry"
              ].map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Caste Category</label>
            <select className="form-control" value={form.casteCategory} onChange={set("casteCategory")}>
              <option value="General">General</option>
              <option value="OBC">OBC</option>
              <option value="SC">SC</option>
              <option value="ST">ST</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Marital / Widow Status</label>
            <select className="form-control"
              value={form.isWidow ? "widow" : "other"}
              onChange={(e) => setForm((p) => ({ ...p, isWidow: e.target.value === "widow" }))}>
              <option value="other">Married / Single / Divorced</option>
              <option value="widow">Widow / Widower</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Disability (if any)</label>
            <input type="text" className="form-control"
              placeholder="e.g. Visual, Orthopedic (leave blank if none)"
              value={form.disabilityType} onChange={set("disabilityType")} />
          </div>

          <div className="form-group">
            <label className="form-label">Number of Children</label>
            <input type="number" className="form-control" min={0} max={20}
              value={form.childrenCount} onChange={set("childrenCount")} />
          </div>

          {/* ── Economic ─────────────────────────────── */}
          <div className="form-group">
            <label className="form-label">Annual Family Income (₹)</label>
            <input type="number" className="form-control" min={0} step={1000}
              required value={form.annualIncome} onChange={set("annualIncome")}
              placeholder="e.g. 120000" />
          </div>

          <div className="form-group">
            <label className="form-label">Primary Income Source</label>
            <select className="form-control" value={form.incomeSource} onChange={set("incomeSource")}>
              <option value="farmer">Farmer / Agriculture</option>
              <option value="daily_wage">Daily Wage / Labour</option>
              <option value="salaried">Salaried (Private/Govt)</option>
              <option value="business">Self-employed / Business</option>
              <option value="pension">Pension / Retired</option>
              <option value="other">Other / Unemployed</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Education Level</label>
            <select className="form-control" value={form.educationLevel} onChange={set("educationLevel")}>
              <option value="none">No formal education</option>
              <option value="primary">Primary (up to Class 5)</option>
              <option value="class 8">Middle (Class 8)</option>
              <option value="class 10">Matriculate (Class 10)</option>
              <option value="class 12">Intermediate (Class 12)</option>
              <option value="graduate">Graduate</option>
              <option value="postgraduate">Post-Graduate or above</option>
            </select>
          </div>

          {/* ── Assets ─────────────────────────────── */}
          <div className="form-group">
            <label className="form-label">Agricultural Land Owned (Acres)</label>
            <input type="number" className="form-control" min={0} step={0.5}
              value={form.landAcres} onChange={set("landAcres")} />
          </div>

          {/* ── Checkboxes ─────────────────────────────── */}
          <div className="form-group">
            <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
              <input type="checkbox" checked={form.hasHouse} onChange={set("hasHouse")}
                style={{ width: 18, height: 18 }} />
              <span className="form-label" style={{ margin: 0 }}>Own a pucca house</span>
            </label>
          </div>

          <div className="form-group">
            <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
              <input type="checkbox" checked={form.hasBankAccount} onChange={set("hasBankAccount")}
                style={{ width: 18, height: 18 }} />
              <span className="form-label" style={{ margin: 0 }}>Have a bank account</span>
            </label>
          </div>

          <div className="form-group">
            <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
              <input type="checkbox" checked={form.hasAadhar} onChange={set("hasAadhar")}
                style={{ width: 18, height: 18 }} />
              <span className="form-label" style={{ margin: 0 }}>Have an Aadhaar card</span>
            </label>
          </div>

        </div>

        <div className="checker-actions">
          <button type="submit" className="btn-sm btn-primary" disabled={saving}
            style={{ padding: "12px 32px", fontSize: "1rem" }}>
            {saving ? "Saving…" : "Save Profile & Find My Schemes →"}
          </button>
        </div>
      </form>
    </div>
  );
}
