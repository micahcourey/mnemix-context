# OAuth 2.0 and JWT Security Best Practices

## Overview

This guide covers security best practices for OAuth 2.0 and JSON Web Tokens (JWT), for Okta SSO integration. Understanding these patterns is critical for secure authentication and authorization.

**Sources**:
- [OWASP JWT Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
- [RFC 7519 - JSON Web Token](https://tools.ietf.org/html/rfc7519)
- [OAuth 2.0 Security Best Current Practice](https://tools.ietf.org/html/draft-ietf-oauth-security-topics)

---

## JWT Structure

A JWT consists of three parts separated by dots:

```
[HEADER].[PAYLOAD].[SIGNATURE]
```

### Example Decoded JWT

**Header**:
```json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "abc123"
}
```

**Payload**:
```json
{
  "sub": "00u1a2b3c4d5e6f7g8h9",
  "name": "John Doe",
  "email": "john.doe@example.com",
  "groups": ["App_Users", "ACO_Admin"],
  "iss": "https://auth.example.com",
  "aud": "api://default",
  "iat": 1704067200,
  "exp": 1704070800
}
```

**Signature**:
```
RSASHA256(
  base64UrlEncode(header) + "." + base64UrlEncode(payload),
  privateKey
)
```

---

## Common JWT Vulnerabilities

### 1. None Algorithm Attack

**Vulnerability**: Attacker changes the algorithm to "none" and removes the signature.

**Attack Example**:
```javascript
// Original token
eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.[signature]

// Modified token with "none" algorithm
eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJzdWIiOiIxMjM0NTY3ODkwIn0.
```

**Prevention**:
```typescript
import jwt from 'jsonwebtoken';

// ❌ Vulnerable - accepts any algorithm
const decoded = jwt.verify(token, secret);

// ✅ Secure - explicitly require algorithm
const decoded = jwt.verify(token, publicKey, {
  algorithms: ['RS256']  // Only accept RS256
});
```

---

### 2. Algorithm Confusion Attack

**Vulnerability**: Attacker tricks server into using symmetric (HMAC) verification with an RSA public key as the secret.

**Prevention**:
```typescript
// ✅ Use separate code paths for different algorithms
const options = {
  algorithms: ['RS256'],        // Asymmetric only
  issuer: 'https://auth.example.com',
  audience: 'api://default'
};

const decoded = jwt.verify(token, rsaPublicKey, options);
```

---

### 3. Token Sidejacking

**Vulnerability**: Stolen token can be reused by attacker.

**Prevention - Add User Context**:
```typescript
// During authentication, create a fingerprint
import crypto from 'crypto';

function createSession(user: User, res: Response): string {
  // Generate random fingerprint
  const fingerprint = crypto.randomBytes(32).toString('hex');
  
  // Hash fingerprint for JWT (prevent XSS from reading cookie value)
  const fingerprintHash = crypto
    .createHash('sha256')
    .update(fingerprint)
    .digest('hex');
  
  // Store raw fingerprint in httpOnly cookie
  res.cookie('__Secure-Fgp', fingerprint, {
    httpOnly: true,
    secure: true,
    sameSite: 'strict',
    maxAge: 3600000 // 1 hour
  });
  
  // Include hash in JWT
  const token = jwt.sign({
    sub: user.id,
    fingerprint: fingerprintHash
  }, privateKey, { 
    algorithm: 'RS256',
    expiresIn: '1h'
  });
  
  return token;
}

// During verification
function verifyToken(token: string, req: Request): JWTPayload {
  const decoded = jwt.verify(token, publicKey, { algorithms: ['RS256'] });
  
  // Verify fingerprint matches
  const cookieFingerprint = req.cookies['__Secure-Fgp'];
  const expectedHash = crypto
    .createHash('sha256')
    .update(cookieFingerprint)
    .digest('hex');
  
  if (decoded.fingerprint !== expectedHash) {
    throw new Error('Token fingerprint mismatch');
  }
  
  return decoded;
}
```

---

### 4. Token Information Disclosure

**Vulnerability**: JWT payload is only Base64 encoded, not encrypted. Sensitive data is exposed.

**Prevention**:
```typescript
// ❌ Never include sensitive data in JWT
const badPayload = {
  sub: user.id,
  ssn: '123-45-6789',        // NEVER
  password: 'hash',          // NEVER
  creditCard: '4111...',     // NEVER
  medicalRecords: [...]      // NEVER
};

// ✅ Include only necessary claims
const goodPayload = {
  sub: user.id,               // User identifier
  email: user.email,          // Basic info
  groups: user.groups,        // Role/group membership
  tenantIds: [1, 2, 3],    // Tenant access scope
  iat: Date.now() / 1000,
  exp: Date.now() / 1000 + 3600
};
```

**Optional: Encrypt JWT (JWE)**:
```typescript
import * as jose from 'jose';

// Create encrypted JWT
async function createEncryptedToken(payload: object): Promise<string> {
  const secretKey = await jose.importJWK(encryptionKey);
  
  return new jose.EncryptJWT(payload)
    .setProtectedHeader({ alg: 'dir', enc: 'A256GCM' })
    .setIssuedAt()
    .setExpirationTime('1h')
    .encrypt(secretKey);
}
```

---

### 5. Weak Token Secret (HMAC)

**Vulnerability**: Weak secrets can be brute-forced offline.

**Requirements**:
- Minimum 256 bits (32 bytes) for HS256
- Minimum 384 bits (48 bytes) for HS384
- Minimum 512 bits (64 bytes) for HS512
- Use cryptographically secure random generation

```typescript
import crypto from 'crypto';

// ❌ Weak secret
const weakSecret = 'mysecret123';

// ✅ Strong secret (generate once, store securely)
const strongSecret = crypto.randomBytes(64).toString('hex');
// Output: 128-character hex string (512 bits)

// ✅ Better: Use RSA/ECDSA instead of HMAC
// Asymmetric keys are more secure for JWTs
```

---

### 6. Missing Token Expiration

**Vulnerability**: Tokens without expiration remain valid indefinitely.

**Best Practice**:
```typescript
const accessToken = jwt.sign(payload, privateKey, {
  algorithm: 'RS256',
  expiresIn: '15m',          // Short-lived access token
  issuer: 'https://app.example.com',
  audience: 'api://default'
});

// Verification automatically checks expiration
jwt.verify(token, publicKey, {
  algorithms: ['RS256'],
  issuer: 'https://app.example.com',
  audience: 'api://default'
});
```

---

### 7. Token Storage on Client Side

**Storage Options**:

| Storage | XSS Vulnerable | CSRF Vulnerable | Recommendation |
|---------|----------------|-----------------|----------------|
| localStorage | ✅ Yes | ❌ No | ⚠️ Avoid for sensitive apps |
| sessionStorage | ✅ Yes | ❌ No | ⚠️ Better, but still XSS risk |
| httpOnly Cookie | ❌ No | ✅ Yes | ✅ Use with CSRF protection |
| Memory | ❌ No | ❌ No | ✅ Best security |

**Recommended Pattern**:
```typescript
// Angular service with memory storage
@Injectable({ providedIn: 'root' })
export class AuthService {
  private accessToken: string | null = null;
  
  setToken(token: string): void {
    this.accessToken = token;
  }
  
  getToken(): string | null {
    return this.accessToken;
  }
  
  clearToken(): void {
    this.accessToken = null;
  }
}

// HTTP interceptor adds token to requests
@Injectable()
export class AuthInterceptor implements HttpInterceptor {
  constructor(private authService: AuthService) {}
  
  intercept(req: HttpRequest<any>, next: HttpHandler): Observable<HttpEvent<any>> {
    const token = this.authService.getToken();
    
    if (token) {
      req = req.clone({
        setHeaders: {
          Authorization: `Bearer ${token}`
        }
      });
    }
    
    return next.handle(req);
  }
}
```

---

## OAuth 2.0 Best Practices

### 1. Use Authorization Code Flow with PKCE

PKCE (Proof Key for Code Exchange) prevents authorization code interception attacks.

```typescript
// Generate PKCE parameters
function generatePKCE(): { verifier: string; challenge: string } {
  const verifier = crypto.randomBytes(32)
    .toString('base64url');
  
  const challenge = crypto
    .createHash('sha256')
    .update(verifier)
    .digest('base64url');
  
  return { verifier, challenge };
}

// Authorization request with PKCE
const authUrl = new URL('https://auth.example.com/oauth2/v1/authorize');
authUrl.searchParams.set('client_id', CLIENT_ID);
authUrl.searchParams.set('response_type', 'code');
authUrl.searchParams.set('redirect_uri', REDIRECT_URI);
authUrl.searchParams.set('scope', 'openid profile email');
authUrl.searchParams.set('state', generateRandomState());
authUrl.searchParams.set('code_challenge', pkce.challenge);
authUrl.searchParams.set('code_challenge_method', 'S256');
```

### 2. Always Validate State Parameter

Prevents CSRF attacks on OAuth flow.

```typescript
// Before redirecting to authorization server
const state = crypto.randomBytes(16).toString('hex');
sessionStorage.setItem('oauth_state', state);

// In callback, verify state matches
const returnedState = new URL(window.location.href).searchParams.get('state');
const savedState = sessionStorage.getItem('oauth_state');

if (returnedState !== savedState) {
  throw new Error('Invalid state parameter - possible CSRF attack');
}
sessionStorage.removeItem('oauth_state');
```

### 3. Token Refresh Best Practices

```typescript
// Refresh token rotation
async function refreshTokens(refreshToken: string): Promise<TokenResponse> {
  const response = await fetch('https://auth.example.com/oauth2/v1/token', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded'
    },
    body: new URLSearchParams({
      grant_type: 'refresh_token',
      refresh_token: refreshToken,
      client_id: CLIENT_ID
    })
  });
  
  if (!response.ok) {
    // Refresh token may be revoked - force re-authentication
    throw new Error('Token refresh failed');
  }
  
  const tokens = await response.json();
  
  // New refresh token issued (rotation) - invalidate old one
  return {
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token, // Use new refresh token
    expiresIn: tokens.expires_in
  };
}
```

### 4. Validate All JWT Claims

```typescript
import OktaJwtVerifier from '@okta/jwt-verifier';

const oktaJwtVerifier = new OktaJwtVerifier({
  issuer: process.env.OKTA_ISSUER,
  clientId: process.env.OKTA_CLIENT_ID
});

async function validateToken(accessToken: string): Promise<JwtClaims> {
  const jwt = await oktaJwtVerifier.verifyAccessToken(
    accessToken,
    'api://default'  // Expected audience
  );
  
  // Additional custom validations
  const claims = jwt.claims;
  
  // Verify required groups
  if (!claims.groups?.includes('App_Users')) {
    throw new Error('User not in required group');
  }
  
  // Verify email domain for internal users
  if (!claims.email?.endsWith('@example.com')) {
    throw new Error('Invalid email domain');
  }
  
  return claims;
}
```

---

## Okta Integration Pattern

### Backend Middleware

```typescript
import OktaJwtVerifier from '@okta/jwt-verifier';

const oktaVerifier = new OktaJwtVerifier({
  issuer: process.env.OKTA_ISSUER!,
  clientId: process.env.OKTA_CLIENT_ID!
});

interface AuthenticatedRequest extends Request {
  user: {
    id: string;
    email: string;
    groups: string[];
    agreements: Agreement[];
  };
}

export async function authMiddleware(
  req: Request,
  res: Response,
  next: NextFunction
): Promise<void> {
  try {
    // Extract token from Authorization header
    const authHeader = req.headers.authorization;
    if (!authHeader?.startsWith('Bearer ')) {
      res.status(401).json({ error: 'Missing or invalid Authorization header' });
      return;
    }
    
    const token = authHeader.substring(7);
    
    // Verify with Okta
    const jwt = await oktaVerifier.verifyAccessToken(token, 'api://default');
    
    // Load user data and agreements
    const user = await userService.findByOktaId(jwt.claims.sub);
    const agreements = await agreementService.getForUser(user.id);
    
    // Attach to request
    (req as AuthenticatedRequest).user = {
      id: user.id,
      email: jwt.claims.email as string,
      groups: (jwt.claims.groups as string[]) || [],
      agreements
    };
    
    next();
  } catch (error) {
    if (error.name === 'JwtParseError' || error.name === 'JwtVerificationError') {
      res.status(401).json({ error: 'Invalid token' });
    } else {
      res.status(500).json({ error: 'Authentication error' });
    }
  }
}
```

### Angular Auth Service

```typescript
import { OktaAuthService } from '@okta/okta-angular';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private user$ = new BehaviorSubject<User | null>(null);
  
  constructor(
    private oktaAuth: OktaAuthService,
    private http: HttpClient
  ) {
    this.oktaAuth.authState$.subscribe(async (isAuthenticated) => {
      if (isAuthenticated) {
        const user = await this.oktaAuth.getUser();
        const profile = await this.loadUserProfile(user.sub);
        this.user$.next(profile);
      } else {
        this.user$.next(null);
      }
    });
  }
  
  async login(): Promise<void> {
    await this.oktaAuth.signInWithRedirect();
  }
  
  async logout(): Promise<void> {
    this.user$.next(null);
    await this.oktaAuth.signOut();
  }
  
  getAccessToken(): Promise<string> {
    return this.oktaAuth.getAccessToken();
  }
  
  isAuthenticated(): Observable<boolean> {
    return this.oktaAuth.isAuthenticated$;
  }
  
  getUser(): Observable<User | null> {
    return this.user$.asObservable();
  }
}
```

---

## Token Revocation

### Logout / Token Invalidation

```typescript
// Option 1: Token blocklist (for critical revocation needs)
class TokenBlocklist {
  private redis: Redis;
  
  async revokeToken(jti: string, expiration: number): Promise<void> {
    // Store until token would have expired anyway
    const ttl = expiration - Math.floor(Date.now() / 1000);
    if (ttl > 0) {
      await this.redis.setex(`revoked:${jti}`, ttl, '1');
    }
  }
  
  async isRevoked(jti: string): Promise<boolean> {
    return await this.redis.exists(`revoked:${jti}`) === 1;
  }
}

// Option 2: Short token lifetime + refresh token rotation
// Access tokens: 15 minutes
// Refresh tokens: 8 hours, rotated on each use
// On logout: Revoke refresh token with Okta API
```

---

## Security Checklist

### JWT Implementation
- [ ] Use RS256 (asymmetric) instead of HS256 (symmetric)
- [ ] Explicitly specify allowed algorithms in verification
- [ ] Validate issuer (iss) claim
- [ ] Validate audience (aud) claim
- [ ] Verify expiration (exp) is present and valid
- [ ] Use short token lifetimes (15-60 minutes)
- [ ] Never store sensitive data in JWT payload
- [ ] Implement token fingerprinting for sidejacking protection

### OAuth 2.0 Implementation
- [ ] Use Authorization Code flow with PKCE
- [ ] Validate state parameter to prevent CSRF
- [ ] Use refresh token rotation
- [ ] Validate redirect URIs strictly
- [ ] Implement proper logout (revoke tokens)

### Client-Side Security
- [ ] Store tokens in memory (not localStorage)
- [ ] Use httpOnly cookies for refresh tokens
- [ ] Implement automatic token refresh
- [ ] Clear tokens on logout
- [ ] Handle token expiration gracefully

---

## References

- [OWASP JWT Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
- [RFC 7519 - JSON Web Token](https://tools.ietf.org/html/rfc7519)
- [RFC 7636 - PKCE](https://tools.ietf.org/html/rfc7636)
- [OAuth 2.0 Security Best Current Practice](https://tools.ietf.org/html/draft-ietf-oauth-security-topics)
- [Okta Security Best Practices](https://developer.okta.com/docs/guides/implement-grant-type/authcode/main/)
- [JWT Attack Playbook](https://github.com/ticarpi/jwt_tool/wiki)

---

*Last Updated: January 2026*
