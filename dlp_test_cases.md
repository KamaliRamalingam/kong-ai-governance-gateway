# Kong AI Gateway - DLP & PII Block Test Cases
Use these examples in the "Domain" field of the DNS Threat Analyzer to verify if Kong AI Gateway blocks them BEFORE reaching the AI.

## 1. Financial & Payment Information
**Credit Card:** 
`checkout-API-request-4242 4242 4242 4242`
*Expected: BLOCKED (Kong Regex Rule)*

**Salary Details:** 
`internal-HR-update-salary details for employee-102`
*Expected: BLOCKED (Kong Keyword Rule)*

## 2. PII / Identity Numbers
**Swedish Personnummer:** 
`user-verification-19850612-9012.internal.volvo`
*Expected: BLOCKED (Kong Regex Rule)*

**GPS Location:** 
`telemetry-stream-gps location tracking-active`
*Expected: BLOCKED (Kong Keyword Rule)*

## 3. Authentication & Security
**Secret API Key:** 
`auth-webhook-sk-live-0123456789abcdefghij0123456789abcdefghij`
*Expected: BLOCKED (Kong Regex Rule)*

**Passwords:** 
`admin-login-password is secret123`
*Expected: BLOCKED (Kong Keyword Rule)*

## 4. Vehicle Specific Sensitive Data (TAPIR)
**VIN (Vehicle Identification Number):**
`diagnostic-report-YV1DZ60EXN1234567`
*Expected: BLOCKED (Kong Regex Rule)*

**CAN Bus Data Dump:**
`vehicle-sync-ecu data dump protocol active`
*Expected: BLOCKED (Kong Keyword Rule)*

## 5. Medical & Biometric
**Medical Record:** 
`employee-health-diagnosis and medical record update`
*Expected: BLOCKED (Kong Keyword Rule)*

## 6. Corporate Confidential Data
**Source Code Leak:** 
`github-upload-source code proprietary algorithm`
*Expected: BLOCKED (Kong Keyword Rule)*

**Security Vulnerability:** 
`infosec-alert-penetration testing report critical`
*Expected: BLOCKED (Kong Keyword Rule)*
