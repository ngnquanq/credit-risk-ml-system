-- Redis Lua script for atomic 3-source feature coordination
--
-- Purpose: Track which sources (application, external, dwh) have completed
-- feature writes for a given sk_id_curr. Only signal ready when ALL 3 are present.
--
-- KEYS[1]: coordination key (e.g., "feature_coordination:12345")
-- ARGV[1]: source name ("application", "external", or "dwh")
-- ARGV[2]: TTL in seconds (e.g., 60)
--
-- Returns: Number of sources present (1, 2, or 3)
--
-- Usage from Python:
--   count = lua_script(keys=['feature_coordination:12345'], args=['application', 60])
--   if count == 3:
--       publish_feature_ready_event(sk_id_curr)

local coord_key = KEYS[1]
local source = ARGV[1]
local ttl = tonumber(ARGV[2])

-- Add source to set (idempotent - safe to call multiple times)
redis.call('SADD', coord_key, source)

-- Set expiration (refreshes on each call)
redis.call('EXPIRE', coord_key, ttl)

-- Return count of unique sources
local count = redis.call('SCARD', coord_key)
return count
