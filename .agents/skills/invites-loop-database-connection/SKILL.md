---
name: invites-loop-database-connection
description: Accesses, explores, and queries the project's PostgreSQL database to retrieve data and schema information.
---

# Database Connection Skill

## When to use this skill
- Use this skill when the user explicitly requests database information, structural schema analysis, or data retrieval.
- Examples include:
  - Finding specific user records, invite codes, or table structures.
  - Analyzing data distributions, counts, and relations within the `invites_loop` and `iccoli` services.
- **DO NOT** use this skill for general factual knowledge or coding questions unrelated to the project's specific database.

## Instructions
- **Connection Command:** Execute `psql service=invites_loop` or `psql service=iccoli` to interact with these databases.
- **Execution Principles:**
  1. **Schema Discovery First:** If the database structure or table names are unknown, always query the schema first (e.g., `\dt` or information_schema) before guessing table structures.
  2. **Read-Only Safeties:** Only execute `SELECT` queries. Do not perform any destructive operations (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`) unless explicitly and unambiguously commanded by the user.
  3. **Performance Optimization:** Always append a `LIMIT` clause (e.g., `LIMIT 100`) to exploratory queries to prevent large data transfers and session timeouts.
  4. **Output Formatting:** Present the query results in a clean, human-readable Markdown table. If the result is empty, clearly state that no records match the criteria.
