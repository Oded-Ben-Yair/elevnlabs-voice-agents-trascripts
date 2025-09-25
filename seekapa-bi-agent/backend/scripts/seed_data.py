import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.db.models import User, Session as UserSession, Query, Report, Insight
from app.db.session import DatabaseSessionManager
import random
import bcrypt

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def seed_users(session: Session, num_users: int = 10):
    """Seed users for development environment"""
    users = []
    for i in range(num_users):
        user = User(
            id=str(uuid.uuid4()),
            username=f"user_{i}",
            email=f"user_{i}@example.com",
            hashed_password=hash_password(f"password_{i}"),
            is_active=True,
            created_at=datetime.utcnow(),
            last_login=datetime.utcnow() - timedelta(days=random.randint(0, 30))
        )
        users.append(user)
        session.add(user)
    return users

def seed_sessions(session: Session, users: list):
    """Seed user sessions"""
    for user in users:
        session_entry = UserSession(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token=str(uuid.uuid4()),
            expires_at=datetime.utcnow() + timedelta(days=30),
            created_at=datetime.utcnow(),
            is_active=True
        )
        session.add(session_entry)

def seed_queries(session: Session, users: list):
    """Seed example queries"""
    query_texts = [
        "SELECT * FROM users LIMIT 10",
        "SELECT AVG(execution_time) FROM queries",
        "SELECT COUNT(*) FROM reports",
        "SELECT type, COUNT(*) FROM insights GROUP BY type"
    ]
    for user in users:
        for _ in range(random.randint(1, 5)):
            query = Query(
                id=str(uuid.uuid4()),
                user_id=user.id,
                query_text=random.choice(query_texts),
                params={"limit": 10},
                execution_time=random.randint(10, 500),
                created_at=datetime.utcnow() - timedelta(days=random.randint(0, 30))
            )
            session.add(query)

def seed_reports(session: Session, users: list):
    """Seed example reports"""
    report_types = ["Performance", "User Analytics", "Query Insights", "System Health"]
    for user in users:
        for _ in range(random.randint(1, 3)):
            report = Report(
                id=str(uuid.uuid4()),
                user_id=user.id,
                title=f"Report: {random.choice(report_types)}",
                description="Automated seed report for development testing",
                data={
                    "metrics": ["users", "queries", "performance"],
                    "summary": f"Generated on {datetime.utcnow()}"
                },
                created_at=datetime.utcnow() - timedelta(days=random.randint(0, 30))
            )
            session.add(report)

def seed_insights(session: Session, queries: list):
    """Seed insights related to queries"""
    insight_types = ["performance", "optimization", "anomaly", "warning"]
    for query in queries[:5]:  # Seed insights for first 5 queries
        insight = Insight(
            id=str(uuid.uuid4()),
            query_id=query.id,
            type=random.choice(insight_types),
            details={
                "query_id": query.id,
                "execution_time": query.execution_time,
                "recommendation": "Potential optimization possible"
            },
            created_at=datetime.utcnow() - timedelta(days=random.randint(0, 30))
        )
        session.add(insight)

def main():
    # Replace with your actual database URL
    db_manager = DatabaseSessionManager("postgresql://user:password@localhost/seekapa_bi")

    with next(db_manager.get_session()) as session:
        try:
            users = seed_users(session)
            seed_sessions(session, users)
            seed_queries(session, users)
            seed_reports(session, users)
            seed_insights(session, session.query(Query).all())

            session.commit()
            print("Database seeding completed successfully!")
        except Exception as e:
            session.rollback()
            print(f"Error during seeding: {e}")

if __name__ == "__main__":
    main()