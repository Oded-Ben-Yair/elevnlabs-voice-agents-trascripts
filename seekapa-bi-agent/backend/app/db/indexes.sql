-- Users Table Indexes
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_created_at ON users(created_at);

-- Sessions Table Indexes
CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_token ON sessions(token);
CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);

-- Queries Table Partitioned and Indexed
CREATE INDEX idx_queries_user_id ON queries(user_id);
CREATE INDEX idx_queries_created_at ON queries(created_at);
CREATE INDEX idx_queries_execution_time ON queries(execution_time);

-- Reports Table Indexes
CREATE INDEX idx_reports_user_id ON reports(user_id);
CREATE INDEX idx_reports_created_at ON reports(created_at);

-- Insights Table Indexes
CREATE INDEX idx_insights_query_id ON insights(query_id);
CREATE INDEX idx_insights_type ON insights(type);
CREATE INDEX idx_insights_created_at ON insights(created_at);

-- Optional Partial Indexes for Performance
CREATE INDEX idx_active_users ON users(id) WHERE is_active = true;
CREATE INDEX idx_active_sessions ON sessions(id) WHERE is_active = true;