import React, { useState } from "react";

export default function EligibilityChecker({ schemes, onSelectScheme }) {
  const [age, setAge] = useState(30);
  const [gender, setGender] = useState("male");
  const [income, setIncome] = useState(150000);
  const [caste, setCaste] = useState("General");
  const [land, setLand] = useState(1.5);
  const [isWidow, setIsWidow] = useState(false);
  const [results, setResults] = useState(null);

  function checkEligibility(e) {
    e.preventDefault();

    const matches = schemes.map(function(scheme) {
      let score = 100;
      let notes = [];
      const c = scheme.criteria || {};

      // Check age limit
      if (c.minAge !== undefined && age < c.minAge) {
        score -= 40;
        notes.push("Must be at least " + c.minAge + " years old");
      }
      if (c.maxAge !== undefined && age > c.maxAge) {
        score -= 40;
        notes.push("Must be under " + c.maxAge + " years old");
      }

      // Check gender rule
      if (c.allowedGenders && !c.allowedGenders.includes("all")) {
        if (!c.allowedGenders.includes(gender)) {
          score -= 50;
          notes.push("Only for " + c.allowedGenders.join(", "));
        }
      }

      // Check income threshold
      if (c.maxIncome !== undefined && income > c.maxIncome) {
        score -= 50;
        notes.push("Annual income exceeds max limit of Rs " + c.maxIncome.toLocaleString("en-IN"));
      }

      // Check land requirement
      if (c.requiresLand && land <= 0) {
        score -= 50;
        notes.push("Requires owning agricultural land");
      }

      // Check widow requirement
      if (c.requiresWidow && !isWidow) {
        score -= 70;
        notes.push("Only available for widows");
      }

      // Check caste category
      if (c.allowedCastes && !c.allowedCastes.includes("all")) {
        if (!c.allowedCastes.includes(caste)) {
          score -= 50;
          notes.push("Only for " + c.allowedCastes.join(", "));
        }
      }

      if (score < 0) score = 0;

      let status = "Not Eligible";
      let statusClass = "not-eligible";

      if (score >= 80) {
        status = "Eligible";
        statusClass = "eligible";
      } else if (score >= 50) {
        status = "Likely Eligible";
        statusClass = "likely";
      }

      return {
        scheme: scheme,
        score: score,
        status: status,
        statusClass: statusClass,
        notes: notes
      };
    });

    matches.sort(function(a, b) {
      return b.score - a.score;
    });

    setResults(matches);
  }

  return (
    <div className="checker-box">
      <div className="checker-header">
        <h2 className="checker-title">Check Your Scheme Eligibility</h2>
        <p className="checker-subtitle">
          Fill in your details below to see which government schemes you can qualify for.
        </p>
      </div>

      <form onSubmit={checkEligibility}>
        <div className="checker-form">
          <div className="form-group">
            <label className="form-label">Your Age</label>
            <input
              type="number"
              className="form-control"
              value={age}
              min="1"
              max="100"
              onChange={(e) => setAge(Number(e.target.value))}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label">Gender</label>
            <select
              className="form-control"
              value={gender}
              onChange={(e) => setGender(e.target.value)}
            >
              <option value="male">Male</option>
              <option value="female">Female</option>
              <option value="other">Other</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Annual Family Income (Rs)</label>
            <input
              type="number"
              className="form-control"
              value={income}
              step="10000"
              onChange={(e) => setIncome(Number(e.target.value))}
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label">Caste Category</label>
            <select
              className="form-control"
              value={caste}
              onChange={(e) => setCaste(e.target.value)}
            >
              <option value="General">General</option>
              <option value="OBC">OBC</option>
              <option value="SC">SC</option>
              <option value="ST">ST</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Land Owned (Acres)</label>
            <input
              type="number"
              className="form-control"
              value={land}
              step="0.5"
              min="0"
              onChange={(e) => setLand(Number(e.target.value))}
            />
          </div>

          <div className="form-group">
            <label className="form-label">Marital Status</label>
            <select
              className="form-control"
              value={isWidow ? "widow" : "other"}
              onChange={(e) => setIsWidow(e.target.value === "widow")}
            >
              <option value="other">Married / Single</option>
              <option value="widow">Widow</option>
            </select>
          </div>
        </div>

        <div className="checker-actions">
          <button type="submit" className="btn-sm btn-primary">
            Check Schemes Now
          </button>
        </div>
      </form>

      {results && (
        <div className="eligibility-results">
          <h3 style={{ marginBottom: "16px", fontSize: "1.1rem" }}>
            Results ({results.filter(r => r.score >= 50).length} matching schemes found)
          </h3>

          <div className="schemes-grid">
            {results.map(function(item) {
              const scheme = item.scheme;
              return (
                <div key={scheme.id} className="scheme-card">
                  <div className="scheme-header">
                    <span className="scheme-category-badge">{scheme.category}</span>
                    <span className={"result-badge " + item.statusClass}>
                      {item.status} ({item.score}%)
                    </span>
                  </div>

                  <h3 className="scheme-title">{scheme.name}</h3>
                  <div className="scheme-ministry">{scheme.ministry}</div>

                  <div className="scheme-benefit">
                    <div className="benefit-label">Benefit</div>
                    <div className="benefit-val">{scheme.benefitAmount}</div>
                  </div>

                  {item.notes.length > 0 && (
                    <div style={{ color: "#b91c1c", fontSize: "0.82rem", marginBottom: "12px" }}>
                      * {item.notes.join("; ")}
                    </div>
                  )}

                  <div className="scheme-footer">
                    <button
                      type="button"
                      className="btn-sm btn-outline"
                      onClick={() => onSelectScheme(scheme)}
                    >
                      View Details
                    </button>
                    <a
                      href={scheme.applicationUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="btn-sm btn-primary"
                    >
                      Apply
                    </a>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
