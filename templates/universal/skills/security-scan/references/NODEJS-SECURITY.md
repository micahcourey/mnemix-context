# Node.js Security Best Practices

## Overview

This guide covers security best practices for Node.js applications, for Express-based APIs and AWS Lambda functions. Based on the OWASP Node.js Security Cheat Sheet and industry best practices.

**Source**: [OWASP Node.js Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Nodejs_Security_Cheat_Sheet.html)

---

## Application Security

### Input Validation

All user input must be validated before processing. JavaScript's dynamic typing makes input validation especially critical.

**Query String Parsing Pitfalls**:
```typescript
// Express parses query strings dynamically:
// ?foo=bar          → 'bar' (string)
// ?foo=bar&foo=baz  → ['bar', 'baz'] (array)
// ?foo[bar]=baz     → { bar: 'baz' } (object)
```

**Secure Validation Pattern**:
```typescript
import Joi from 'joi';

const searchSchema = Joi.object({
  query: Joi.string().min(1).max(100).required(),
  page: Joi.number().integer().min(1).default(1),
  pageSize: Joi.number().integer().min(1).max(100).default(25)
});

router.get('/api/search', async (req, res) => {
  const { error, value } = searchSchema.validate(req.query);
  if (error) {
    return res.status(400).json({ 
      error: 'Invalid input',
      details: error.details.map(d => d.message)
    });
  }
  // Use validated 'value' object
});
```

---

### Output Escaping

Prevent XSS by escaping all user-controlled content in HTML responses.

```typescript
import escapeHtml from 'escape-html';

// ✅ Escape user content in HTML
const safeContent = escapeHtml(userInput);

// ✅ Use templating engines with auto-escaping (EJS, Handlebars)
res.render('template', { userName: escapeHtml(userName) });
```

---

### Request Size Limits

Prevent resource exhaustion by limiting request body sizes.

```typescript
import express from 'express';

const app = express();

// Set size limits for different content types
app.use(express.json({ limit: '100kb' }));
app.use(express.urlencoded({ extended: true, limit: '100kb' }));

// For file uploads, use multer with limits
import multer from 'multer';

const upload = multer({
  limits: {
    fileSize: 10 * 1024 * 1024, // 10MB
    files: 5 // Max 5 files
  }
});
```

---

### Rate Limiting and Brute Force Protection

Protect endpoints from abuse with rate limiting.

```typescript
import rateLimit from 'express-rate-limit';

// General API rate limit
const apiLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: 'Too many requests', retryAfter: '15 minutes' }
});

// Stricter limit for authentication endpoints
const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 5,
  skipSuccessfulRequests: false,
  message: { error: 'Too many login attempts' }
});

app.use('/api/', apiLimiter);
app.use('/api/auth/login', authLimiter);
```

---

### HTTP Parameter Pollution (HPP) Prevention

Prevent attacks using duplicate HTTP parameters.

```typescript
import hpp from 'hpp';

// HPP middleware - uses last parameter value when duplicates exist
app.use(hpp());

// Or use allowlist for specific parameters
app.use(hpp({
  whitelist: ['filter', 'sort'] // Allow arrays for these params
}));
```

---

### Prevent Prototype Pollution

Protect against prototype pollution attacks through object manipulation.

```typescript
// ❌ Dangerous: Direct object merge
Object.assign(target, userInput);

// ❌ Dangerous: Recursive merge without protection
function merge(target, source) {
  for (const key in source) {
    target[key] = source[key];
  }
}

// ✅ Safe: Block dangerous keys
function safeMerge(target: Record<string, unknown>, source: Record<string, unknown>) {
  const BLOCKED_KEYS = ['__proto__', 'constructor', 'prototype'];
  
  for (const key in source) {
    if (BLOCKED_KEYS.includes(key)) {
      continue;
    }
    if (source.hasOwnProperty(key)) {
      target[key] = source[key];
    }
  }
  return target;
}

// ✅ Safe: Use Object.create(null) for dictionaries
const safeDict = Object.create(null);
```

---

## Error & Exception Handling

### Handle Uncaught Exceptions

Never let uncaught exceptions crash silently or expose stack traces.

```typescript
// Global uncaught exception handler
process.on('uncaughtException', (err: Error) => {
  console.error('Uncaught Exception:', err.message);
  // Log to monitoring service
  logger.error('Uncaught Exception', { error: err.stack });
  
  // Cleanup and exit
  process.exit(1);
});

// Unhandled promise rejections
process.on('unhandledRejection', (reason: unknown, promise: Promise<unknown>) => {
  console.error('Unhandled Rejection at:', promise, 'reason:', reason);
  logger.error('Unhandled Rejection', { reason });
});
```

### Structured Error Responses

Never expose internal error details to clients.

```typescript
// ✅ Recommended Error Format
interface ApiError {
  error: string;     // Error code
  message: string;   // User-friendly message
  statusCode: number;
}

// Error handling middleware
app.use((err: Error, req: Request, res: Response, next: NextFunction) => {
  // Log full error internally
  logger.error('Request error', {
    error: err.message,
    stack: err.stack,
    path: req.path,
    method: req.method
  });

  // Return sanitized error to client
  const statusCode = (err as any).statusCode || 500;
  res.status(statusCode).json({
    error: 'INTERNAL_ERROR',
    message: statusCode === 500 ? 'An unexpected error occurred' : err.message,
    statusCode
  });
});
```

### Handle Async Errors in Express

Express doesn't catch async errors automatically.

```typescript
// ✅ Async wrapper for route handlers
const asyncHandler = (fn: RequestHandler): RequestHandler => {
  return (req, res, next) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
};

// Usage
router.get('/api/data', asyncHandler(async (req, res) => {
  const data = await dataService.fetch();
  res.json(data);
  // Errors automatically passed to error middleware
}));
```

---

## Server Security

### Security Headers with Helmet

Use Helmet.js to set secure HTTP headers.

```typescript
import helmet from 'helmet';

app.use(helmet());

// Custom Content Security Policy
app.use(helmet.contentSecurityPolicy({
  directives: {
    defaultSrc: ["'self'"],
    scriptSrc: ["'self'"],
    styleSrc: ["'self'", "'unsafe-inline'"],
    imgSrc: ["'self'", 'data:', 'https:'],
    connectSrc: ["'self'", process.env.API_URL],
    frameAncestors: ["'none'"]
  }
}));

// HSTS
app.use(helmet.hsts({
  maxAge: 31536000, // 1 year
  includeSubDomains: true,
  preload: true
}));

// Hide X-Powered-By
app.use(helmet.hidePoweredBy());
```

### Secure Cookie Configuration

```typescript
import session from 'express-session';

app.use(session({
  secret: process.env.SESSION_SECRET,
  name: 'sessionId', // Don't use default 'connect.sid'
  cookie: {
    secure: true,      // HTTPS only
    httpOnly: true,    // No JavaScript access
    sameSite: 'strict', // CSRF protection
    maxAge: 3600000    // 1 hour
  },
  resave: false,
  saveUninitialized: false
}));
```

### CORS Configuration

```typescript
import cors from 'cors';

const corsOptions: cors.CorsOptions = {
  origin: (origin, callback) => {
    const allowedOrigins = [
      'https://app.example.com',
      'https://app-dev.example.com'
    ];
    
    if (!origin || allowedOrigins.includes(origin)) {
      callback(null, true);
    } else {
      callback(new Error('Not allowed by CORS'));
    }
  },
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'],
  allowedHeaders: ['Content-Type', 'Authorization']
};

app.use(cors(corsOptions));
```

---

## Platform Security

### Avoid Dangerous Functions

Never use these with user input:

```typescript
// ❌ NEVER use with untrusted input
eval(userInput);                          // Code injection
new Function(userInput);                   // Code injection
setTimeout(userInput, 1000);              // If string, treated as code
setInterval(userInput, 1000);             // If string, treated as code
child_process.exec(userInput);            // Command injection
require(userInput);                        // Arbitrary module loading
vm.runInContext(userInput, context);      // Code injection
```

### Dependency Security

```bash
# Check for known vulnerabilities
npm audit

# Auto-fix when possible
npm audit fix

# Check outdated packages
npm outdated

# Use audit in CI/CD
npm audit --audit-level=high
```

```typescript
// package.json - Lock dependencies
{
  "engines": {
    "node": ">=18.0.0 <21.0.0",
    "npm": ">=9.0.0"
  }
}
```

### ReDoS Prevention (Regular Expression Denial of Service)

Avoid "evil" regexes that can cause catastrophic backtracking.

```typescript
// ❌ Dangerous regex with nested quantifiers
const evilRegex = /^(([a-z])+.)+[A-Z]([a-z])+$/;

// ✅ Use safe-regex to validate patterns
import safeRegex from 'safe-regex';

function validateRegex(pattern: string): boolean {
  return safeRegex(pattern);
}

// ✅ Set timeout for regex operations
function safeMatch(input: string, pattern: RegExp, timeoutMs = 100): RegExpMatchArray | null {
  const start = Date.now();
  const result = input.match(pattern);
  if (Date.now() - start > timeoutMs) {
    throw new Error('Regex timeout');
  }
  return result;
}
```

### Use Strict Mode

```typescript
// At top of every file (or use TypeScript which enables strict by default)
'use strict';

// tsconfig.json
{
  "compilerOptions": {
    "strict": true
  }
}
```

---

## Node.js Permission Model (v20+)

Node.js 20+ includes a permission model for restricting capabilities.

```bash
# Restrict file system access
node --permission --allow-fs-read=/app/config/ --allow-fs-write=/app/logs/ app.js

# Block child process spawning
node --permission app.js  # No --allow-child-process = blocked

# Restrict network access
node --permission --allow-net=api.example.com app.js
```

---

## AWS Lambda Security

### Lambda-Specific Best Practices

```typescript
import { APIGatewayProxyHandler } from 'aws-lambda';

// ✅ Initialize outside handler (but not secrets)
const dbPool = createPool({ /* config from env */ });

export const handler: APIGatewayProxyHandler = async (event) => {
  // ✅ Validate all input
  const body = JSON.parse(event.body || '{}');
  const validated = inputSchema.parse(body);
  
  // ✅ Use environment variables for config
  const apiKey = process.env.API_KEY;
  
  // ✅ Set timeouts on external calls
  const response = await axios.get(url, { timeout: 5000 });
  
  return {
    statusCode: 200,
    headers: {
      'Content-Type': 'application/json',
      'Strict-Transport-Security': 'max-age=31536000'
    },
    body: JSON.stringify(result)
  };
};
```

### Lambda Environment Variables

```typescript
// ❌ Don't hardcode secrets
const apiKey = 'sk-abc123';

// ✅ Use environment variables
const apiKey = process.env.API_KEY;

// ✅ Use AWS Secrets Manager for sensitive data
import { SecretsManager } from 'aws-sdk';

const secrets = new SecretsManager();
const { SecretString } = await secrets.getSecretValue({
  SecretId: 'app/prod/db-credentials'
}).promise();
```

---

## Security Linting

### ESLint Security Rules

```json
// .eslintrc.json
{
  "extends": [
    "eslint:recommended",
    "plugin:security/recommended"
  ],
  "plugins": ["security"],
  "rules": {
    "security/detect-eval-with-expression": "error",
    "security/detect-non-literal-fs-filename": "warn",
    "security/detect-non-literal-require": "error",
    "security/detect-possible-timing-attacks": "warn",
    "security/detect-unsafe-regex": "error"
  }
}
```

---

## Quick Reference Checklist

### Request Handling
- [ ] Validate all input with schemas (Joi, Zod)
- [ ] Set request body size limits
- [ ] Implement rate limiting
- [ ] Use HPP middleware
- [ ] Sanitize output for HTML contexts

### Authentication & Sessions
- [ ] Use secure cookie flags (httpOnly, secure, sameSite)
- [ ] Implement CSRF protection
- [ ] Use strong session secrets
- [ ] Set appropriate session timeouts

### Error Handling
- [ ] Handle uncaught exceptions
- [ ] Handle unhandled promise rejections
- [ ] Use structured error responses
- [ ] Never expose stack traces to clients

### Dependencies
- [ ] Run `npm audit` regularly
- [ ] Keep dependencies updated
- [ ] Use lock files
- [ ] Avoid deprecated packages

### Code Quality
- [ ] Use strict mode (TypeScript)
- [ ] Avoid dangerous functions (eval, exec)
- [ ] Use security linting
- [ ] Validate regexes for ReDoS

---

## References

- [OWASP Node.js Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Nodejs_Security_Cheat_Sheet.html)
- [OWASP NPM Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/NPM_Security_Cheat_Sheet.html)
- [Node.js Security Best Practices](https://nodejs.org/en/docs/guides/security/)
- [Express Security Best Practices](https://expressjs.com/en/advanced/best-practice-security.html)

---

*Last Updated: January 2026*
