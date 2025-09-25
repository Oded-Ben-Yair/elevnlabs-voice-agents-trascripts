#!/bin/bash
set -e

# Database Backup Script for Seekapa BI Agent

# Configuration
DB_NAME="seekapa_bi"
DB_USER="seekapa_admin"
BACKUP_DIR="/var/backups/seekapa_bi"
RETENTION_DAYS=7

# Create backup directory if not exists
mkdir -p "$BACKUP_DIR"

# Generate backup filename with timestamp
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_$(date +"%Y%m%d_%H%M%S").sql.gz"

# Perform PostgreSQL database backup
pg_dump -U "$DB_USER" -d "$DB_NAME" -F p | gzip > "$BACKUP_FILE"

# Remove old backups
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete

echo "Database backup completed: $BACKUP_FILE"

# Optional: Log backup details
echo "Backup Details:" >> "$BACKUP_DIR/backup.log"
echo "Database: $DB_NAME" >> "$BACKUP_DIR/backup.log"
echo "Timestamp: $(date)" >> "$BACKUP_DIR/backup.log"
echo "File: $BACKUP_FILE" >> "$BACKUP_DIR/backup.log"