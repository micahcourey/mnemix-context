# Reference Documents

Drop project-relevant files here that the **bootstrap agent** should use when populating context files. These are source-of-truth documents that aren't part of your codebase but contain critical project knowledge.

> **Note:** Files in this directory are git-ignored (except this README). They are setup-time inputs — used only during the bootstrap process and never deployed to your project.

## What to Put Here

| Document Type | Examples | Used By |
|--------------|---------|---------|
| **Database extracts** | Role/privilege queries, table listings, schema dumps | `roles.jsonl`, `permissions.jsonl`, `schema.yaml` |
| **API specs** | OpenAPI/Swagger files, Postman collections | `endpoints.jsonl`, `API_Reference.md` |
| **Architecture docs** | System diagrams, data flow docs, ADRs | `System_Architecture.md` |
| **Access control matrices** | Role-permission spreadsheets, RBAC exports | `Role_Permission_Matrix.md`, `role_permissions.jsonl` |
| **Domain glossaries** | Business terminology docs, acronym lists | `glossary.jsonl`, `Domain_Glossary.md` |
| **Compliance docs** | Security requirements, audit checklists | `Access_Control.md`, security instructions |
| **Onboarding guides** | Team wikis, runbooks, setup docs | Various context files |

## Supported Formats

The bootstrap agent can read most text-based formats:
- **Markdown** (`.md`)
- **CSV / TSV** (`.csv`, `.tsv`)
- **JSON / JSONL** (`.json`, `.jsonl`)
- **YAML** (`.yaml`, `.yml`)
- **SQL** (`.sql`) — DDL, query results
- **Plain text** (`.txt`)
- **Excel** (`.xlsx`) — if exported to CSV first

## Example: Database Role Extract

If your project has a roles/permissions system, export the data and drop it here:

```sql
-- roles.sql: Run this against your database and save the output
SELECT role_code, role_name, description FROM roles ORDER BY role_code;
SELECT privilege_code, privilege_name, description FROM privileges ORDER BY privilege_code;
SELECT r.role_code, p.privilege_code FROM role_privileges rp
  JOIN roles r ON r.id = rp.role_id
  JOIN privileges p ON p.id = rp.privilege_id
  ORDER BY r.role_code, p.privilege_code;
```

Save the query results as CSV or paste them into a text file in this directory. The bootstrap agent will parse them into the structured `.jsonl` context files.
