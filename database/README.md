# Database

Cliova will use PostgreSQL, with PostGIS when geographic persistence becomes necessary. Database migrations and deterministic seed fixtures belong here once persistence is introduced.

The database stores authoritative state and history; it does not contain hidden game rules in triggers or stored procedures unless an Architecture Decision Record explicitly justifies it.
