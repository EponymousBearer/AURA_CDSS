# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| 1.0.x | Yes |

---

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Email **amadha@aitek-solutions.com** with the subject line `[SECURITY] antibiotic-ai-cdss`. Include:

1. A description of the vulnerability and its potential impact.
2. Steps to reproduce or a proof-of-concept (sanitised if needed).
3. The component affected (backend, frontend, training pipeline, deployment config).
4. Any suggested mitigations.

We will acknowledge receipt within 48 hours and aim to release a fix within 14 days for critical issues.

---

## Scope

Issues considered in-scope:

- Authentication and authorisation bypass (if auth is added in a future version).
- Injection vulnerabilities (SQL, command, prompt injection via API inputs).
- Sensitive data exposure (model weights served without access control, PII leakage).
- Insecure deserialization of the model pickle file.
- CORS misconfiguration allowing credential access from untrusted origins.
- Dependency vulnerabilities in `requirements.txt` or `package.json`.

Out of scope for this academic version:

- Denial-of-service attacks (no SLA on the demo instance).
- Social engineering.
- Issues in development-only tooling (pytest, ESLint, etc.).

---

## Security Design Notes

### Model pickle

`backend/model/antibiotic_model.pkl` is a Python pickle file. Pickle files can execute arbitrary code when deserialised. Mitigations in place:

- The file is loaded only at server startup from a fixed, internal path.
- The path is not user-controllable via any API parameter.
- In production, the file should be stored in a location only accessible to the application process.
- Consider migrating to a safer serialisation format (ONNX, CBOR) in future versions.

### CORS

The `ALLOWED_ORIGINS` environment variable controls which origins the backend will accept cross-origin requests from. In production this must be set to the exact frontend domain. The default (`http://localhost:3000`) is only safe for local development.

### Input validation

All API inputs are validated by Pydantic before reaching business logic. Organism, gender, kidney function, and severity are enum-constrained. Age is range-validated (0–150). Validation errors return HTTP 422 before any model inference occurs.

### No authentication (v1)

Version 1 has no user authentication. The system is designed for academic demonstration. Before any clinical or production deployment, implement authentication, audit logging, and role-based access controls.

### Dependency management

- Backend: pin exact versions in `requirements.txt`. Run `pip-audit` periodically.
- Frontend: use `npm audit` and keep `package-lock.json` committed.
