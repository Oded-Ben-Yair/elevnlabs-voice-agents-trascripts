# Seekapa BI Agent - Database Integration

## Overview
This project implements comprehensive database integration using:
- PostgreSQL as the primary database
- SQLAlchemy ORM for database interactions
- Redis for caching and distributed locking
- Alembic for database migrations

## Key Components
- `app/db/models.py`: SQLAlchemy database models
- `app/db/session.py`: Database session management
- `app/services/cache_service.py`: Redis caching implementation
- `scripts/backup_db.sh`: Database backup script
- `scripts/seed_data.py`: Development data seeding script

## Setup
1. Install dependencies
```bash
pip install -r requirements.txt
```

2. Configure database connection
- Set environment variables or update `.env` file
- Use `app/core/database.py` for configuration

3. Run migrations
```bash
alembic upgrade head
```

4. Seed development data
```bash
python scripts/seed_data.py
```

## Database Backup
Run database backup script:
```bash
./scripts/backup_db.sh
```

## Performance Considerations
- Connection pooling configured
- Read replica support
- Indexed tables
- Cached query results