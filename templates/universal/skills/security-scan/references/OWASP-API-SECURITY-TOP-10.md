# OWASP API Security Top 10 (2023)

## Overview

The OWASP API Security Top 10 is a standard awareness document for developers and web application security professionals, focusing specifically on the security risks associated with APIs. Microservices architectures rely heavily on REST APIs, making this guidance essential for secure development.

**Source**: [OWASP API Security Project](https://owasp.org/API-Security/)

---

## API Security Top 10 - 2023

### API1:2023 - Broken Object Level Authorization (BOLA)

**Description**: APIs often expose endpoints that handle object identifiers (IDs). When authorization checks are missing or insufficient, attackers can access or modify data belonging to other users.

**Risk Level**: 🔴 Critical

**Context**: Multi-tenant data isolation requires `tenant_id` filtering on all queries.

**Vulnerable Pattern**:
```typescript
// ❌ Missing authorization check
router.get('/api/participants/:id', async (req, res) => {
  const participant = await db.query('SELECT * FROM participant WHERE id = $1', [req.params.id]);
  res.json(participant.rows[0]);
});
```

**Secure Pattern**:
```typescript
// ✅ Tenant-scoped authorization
router.get('/api/participants/:id',
  authMiddleware.verifyTokenRetrieveUser,
  permissionsMiddleware.validateRequiredPrivilege(PrivilegeTypes.VIEW_PARTICIPANT, dataSource, pool),
  async (req, res) => {
    const tenantIds = req.user.agreements.map(a => a.tenant_id);
    const participant = await db.query(
      'SELECT * FROM participant WHERE id = $1 AND tenant_id = ANY($2)',
      [req.params.id, tenantIds]
    );
    if (!participant.rows[0]) return res.status(404).json({ error: 'Not found' });
    res.json(participant.rows[0]);
  }
);
```

---

### API2:2023 - Broken Authentication

**Description**: Authentication mechanisms are often implemented incorrectly, allowing attackers to compromise authentication tokens or exploit implementation flaws to assume other users' identities.

**Risk Level**: 🔴 Critical

**Context**: Okta SSO integration with JWT validation.

**Common Vulnerabilities**:
- Weak token secrets
- Missing token expiration
- Insecure token storage
- Missing rate limiting on login endpoints

**Secure Pattern**:
```typescript
import { expressjwt } from 'express-jwt';
import jwksRsa from 'jwks-rsa';

const jwtCheck = expressjwt({
  secret: jwksRsa.expressJwtSecret({
    cache: true,
    rateLimit: true,
    jwksRequestsPerMinute: 5,
    jwksUri: `${process.env.OKTA_ISSUER}/.well-known/jwks.json`
  }),
  audience: process.env.OKTA_AUDIENCE,
  issuer: process.env.OKTA_ISSUER,
  algorithms: ['RS256']
});
```

---

### API3:2023 - Broken Object Property Level Authorization

**Description**: APIs expose object properties that should not be accessible or modifiable by users. This includes excessive data exposure and mass assignment vulnerabilities.

**Risk Level**: 🟠 High

**Vulnerable Pattern (Excessive Data Exposure)**:
```typescript
// ❌ Exposing sensitive fields
router.get('/api/users/:id', async (req, res) => {
  const user = await userService.findById(req.params.id);
  res.json(user); // Returns SSN, password hash, internal flags
});
```

**Secure Pattern**:
```typescript
// ✅ Explicit field selection
router.get('/api/users/:id', async (req, res) => {
  const user = await userService.findById(req.params.id);
  res.json({
    id: user.id,
    name: user.full_name,
    email: user.email,
    role: user.role
  });
});
```

**Vulnerable Pattern (Mass Assignment)**:
```typescript
// ❌ Direct object spread
router.put('/api/users/:id', async (req, res) => {
  await db.query('UPDATE users SET $1 WHERE id = $2', [req.body, req.params.id]);
});
```

**Secure Pattern**:
```typescript
// ✅ Explicit allowed fields
const ALLOWED_UPDATE_FIELDS = ['full_name', 'email', 'phone'];
router.put('/api/users/:id', async (req, res) => {
  const updates = {};
  ALLOWED_UPDATE_FIELDS.forEach(field => {
    if (req.body[field] !== undefined) updates[field] = req.body[field];
  });
  await userService.update(req.params.id, updates);
});
```

---

### API4:2023 - Unrestricted Resource Consumption

**Description**: APIs do not limit the size or number of resources that can be requested, leading to DoS, increased operational costs, or resource exhaustion.

**Risk Level**: 🟠 High

**Prevention Strategies**:

```typescript
import rateLimit from 'express-rate-limit';
import { json } from 'express';

// Request size limits
app.use(json({ limit: '100kb' }));

// Rate limiting
const apiLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100, // 100 requests per window
  message: { error: 'Too many requests', retryAfter: '15 minutes' }
});

// Pagination enforcement
router.get('/api/participants', async (req, res) => {
  const page = Math.max(1, parseInt(req.query.page) || 1);
  const pageSize = Math.min(100, Math.max(1, parseInt(req.query.pageSize) || 25));
  const offset = (page - 1) * pageSize;
  
  const results = await db.query(
    'SELECT * FROM participant LIMIT $1 OFFSET $2',
    [pageSize, offset]
  );
  res.json({ data: results.rows, page, pageSize });
});
```

---

### API5:2023 - Broken Function Level Authorization

**Description**: Authorization policies are not enforced at the function level, allowing attackers to access administrative functions or perform privileged operations.

**Risk Level**: 🔴 Critical

**Context**: Must use `permissionsMiddleware` for all protected endpoints.

**Vulnerable Pattern**:
```typescript
// ❌ Missing function-level authorization
router.delete('/api/admin/users/:id', async (req, res) => {
  await userService.deleteUser(req.params.id);
  res.status(204).send();
});
```

**Secure Pattern**:
```typescript
// ✅ Explicit privilege check
router.delete('/api/admin/users/:id',
  authMiddleware.verifyTokenRetrieveUser,
  permissionsMiddleware.validateRequiredPrivilege(PrivilegeTypes.DELETE_USER, dataSource, pool),
  auditUserActionMiddleware(auditService, 'DELETE_USER'),
  async (req, res) => {
    await userService.deleteUser(req.params.id);
    res.status(204).send();
  }
);
```

---

### API6:2023 - Unrestricted Access to Sensitive Business Flows

**Description**: APIs expose business flows without proper access controls, allowing attackers to abuse the business logic (e.g., excessive purchasing, review bombing).

**Risk Level**: 🟠 High

**Prevention Strategies**:
- Device fingerprinting
- Human detection (CAPTCHA)
- Non-sequenced IDs
- Rate limiting per business operation

---

### API7:2023 - Server Side Request Forgery (SSRF)

**Description**: APIs fetch remote resources based on user input without proper validation, allowing attackers to access internal services or sensitive data.

**Risk Level**: 🟠 High

**Vulnerable Pattern**:
```typescript
// ❌ Unvalidated URL fetch
router.post('/api/fetch-url', async (req, res) => {
  const response = await fetch(req.body.url);
  res.send(await response.text());
});
```

**Secure Pattern**:
```typescript
// ✅ URL allowlist validation
const ALLOWED_HOSTS = ['api.example.com', 'data.example.com'];

router.post('/api/fetch-url', async (req, res) => {
  const url = new URL(req.body.url);
  if (!ALLOWED_HOSTS.includes(url.hostname)) {
    return res.status(403).json({ error: 'Host not allowed' });
  }
  // Additional: Block internal IPs
  const ip = await dns.resolve(url.hostname);
  if (isInternalIP(ip)) {
    return res.status(403).json({ error: 'Internal access denied' });
  }
  const response = await fetch(req.body.url);
  res.send(await response.text());
});
```

---

### API8:2023 - Security Misconfiguration

**Description**: APIs are misconfigured with default credentials, unnecessary features enabled, or missing security hardening.

**Risk Level**: 🟡 Medium

**Security Hardening Checklist**:
- [ ] Disable verbose error messages in production
- [ ] Remove unused HTTP methods (`TRACE`, `OPTIONS` if not needed)
- [ ] Configure CORS properly
- [ ] Disable directory listing
- [ ] Keep dependencies updated
- [ ] Use security headers (Helmet.js)

```typescript
import helmet from 'helmet';

app.use(helmet());
app.use(helmet.contentSecurityPolicy({
  directives: {
    defaultSrc: ["'self'"],
    scriptSrc: ["'self'"],
    styleSrc: ["'self'", "'unsafe-inline'"]
  }
}));
```

---

### API9:2023 - Improper Inventory Management

**Description**: APIs lack proper documentation, versioning, and inventory management, leading to shadow APIs, outdated endpoints, and inconsistent security policies.

**Risk Level**: 🟡 Medium

**Best Practices**:
- Maintain API inventory/catalog
- Document all endpoints with OpenAPI/Swagger
- Version APIs consistently
- Deprecate and remove old versions
- Apply consistent security policies across all versions

---

### API10:2023 - Unsafe Consumption of APIs

**Description**: APIs trust third-party data without proper validation, leading to security issues when consuming external services.

**Risk Level**: 🟡 Medium

**Secure Pattern**:
```typescript
// ✅ Validate external API responses
import { z } from 'zod';

const ExternalDataSchema = z.object({
  id: z.string().uuid(),
  name: z.string().max(255),
  amount: z.number().positive()
});

async function fetchExternalData(url: string) {
  const response = await fetch(url, { timeout: 5000 });
  const data = await response.json();
  
  // Validate response structure
  const validated = ExternalDataSchema.parse(data);
  return validated;
}
```

---

## Quick Reference Matrix

| Risk | ID | Recommended Mitigation |
|------|-----|------------------|
| 🔴 Critical | API1 | `permissionsMiddleware` + `tenant_id` filtering |
| 🔴 Critical | API2 | Okta SSO + JWT validation |
| 🟠 High | API3 | Explicit DTOs, no `SELECT *` |
| 🟠 High | API4 | Rate limiting, pagination, request size limits |
| 🔴 Critical | API5 | `permissionsMiddleware.validateRequiredPrivilege()` |
| 🟠 High | API6 | Business logic rate limiting |
| 🟠 High | API7 | URL allowlists, block internal IPs |
| 🟡 Medium | API8 | Helmet.js, security headers |
| 🟡 Medium | API9 | OpenAPI documentation, API versioning |
| 🟡 Medium | API10 | Schema validation for external data |

---

## References

- [OWASP API Security Top 10 2023](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
- [OWASP API Security Project](https://owasp.org/www-project-api-security/)
- [API Security Best Practices](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)

---

*Last Updated: January 2026*
