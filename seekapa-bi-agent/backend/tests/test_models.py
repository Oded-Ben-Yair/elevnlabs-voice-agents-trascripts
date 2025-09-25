"""
Tests for database models.
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.exc import IntegrityError

from app.db.models import User, Session, Query, Report, Insight


class TestUserModel:
    """Test User model functionality."""

    @pytest.mark.unit
    @pytest.mark.database
    def test_create_user(self, db_session):
        """Test creating a new user."""
        user = User(
            id="test-user-456",
            username="newuser",
            email="new@example.com",
            hashed_password="hashed_password",
            is_active=True
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.id == "test-user-456"
        assert user.username == "newuser"
        assert user.email == "new@example.com"
        assert user.is_active is True
        assert isinstance(user.created_at, datetime)
        assert user.last_login is None

    @pytest.mark.unit
    @pytest.mark.database
    def test_user_unique_constraints(self, db_session, sample_user):
        """Test user unique constraints on email and username."""
        # Try to create user with same email
        duplicate_email_user = User(
            id="test-user-duplicate-email",
            username="differentuser",
            email=sample_user.email,
            hashed_password="hashed_password"
        )
        db_session.add(duplicate_email_user)

        with pytest.raises(IntegrityError):
            db_session.commit()

        db_session.rollback()

        # Try to create user with same username
        duplicate_username_user = User(
            id="test-user-duplicate-username",
            username=sample_user.username,
            email="different@example.com",
            hashed_password="hashed_password"
        )
        db_session.add(duplicate_username_user)

        with pytest.raises(IntegrityError):
            db_session.commit()

    @pytest.mark.unit
    @pytest.mark.database
    def test_user_relationships(self, db_session, sample_user):
        """Test user relationships with other models."""
        # Create related objects
        session = Session(
            id="test-session-rel",
            user_id=sample_user.id,
            token="test-token-rel",
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )

        query = Query(
            id="test-query-rel",
            user_id=sample_user.id,
            query_text="SELECT 1",
            execution_time=100
        )

        report = Report(
            id="test-report-rel",
            user_id=sample_user.id,
            title="Test Report",
            data={"test": "data"}
        )

        db_session.add_all([session, query, report])
        db_session.commit()

        # Refresh user to load relationships
        db_session.refresh(sample_user)

        # Test relationships
        assert len(sample_user.sessions) == 1
        assert len(sample_user.queries) == 1
        assert len(sample_user.reports) == 1
        assert sample_user.sessions[0].id == "test-session-rel"
        assert sample_user.queries[0].id == "test-query-rel"
        assert sample_user.reports[0].id == "test-report-rel"

    @pytest.mark.unit
    @pytest.mark.database
    def test_user_update_last_login(self, db_session, sample_user):
        """Test updating user's last login timestamp."""
        original_last_login = sample_user.last_login
        new_login_time = datetime.utcnow()

        sample_user.last_login = new_login_time
        db_session.commit()
        db_session.refresh(sample_user)

        assert sample_user.last_login != original_last_login
        assert sample_user.last_login == new_login_time

    @pytest.mark.unit
    @pytest.mark.database
    def test_user_deactivation(self, db_session, sample_user):
        """Test user deactivation functionality."""
        assert sample_user.is_active is True

        sample_user.is_active = False
        db_session.commit()
        db_session.refresh(sample_user)

        assert sample_user.is_active is False


class TestSessionModel:
    """Test Session model functionality."""

    @pytest.mark.unit
    @pytest.mark.database
    def test_create_session(self, db_session, sample_user):
        """Test creating a new session."""
        expires_at = datetime.utcnow() + timedelta(hours=2)

        session = Session(
            id="test-session-new",
            user_id=sample_user.id,
            token="new-session-token",
            expires_at=expires_at,
            is_active=True
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)

        assert session.id == "test-session-new"
        assert session.user_id == sample_user.id
        assert session.token == "new-session-token"
        assert session.expires_at == expires_at
        assert session.is_active is True
        assert isinstance(session.created_at, datetime)

    @pytest.mark.unit
    @pytest.mark.database
    def test_session_unique_token(self, db_session, sample_user, sample_session):
        """Test session token uniqueness."""
        duplicate_session = Session(
            id="test-session-duplicate",
            user_id=sample_user.id,
            token=sample_session.token,
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        db_session.add(duplicate_session)

        with pytest.raises(IntegrityError):
            db_session.commit()

    @pytest.mark.unit
    @pytest.mark.database
    def test_session_expiration_check(self, db_session, sample_user):
        """Test session expiration logic."""
        # Create expired session
        expired_session = Session(
            id="expired-session",
            user_id=sample_user.id,
            token="expired-token",
            expires_at=datetime.utcnow() - timedelta(hours=1)
        )

        # Create valid session
        valid_session = Session(
            id="valid-session",
            user_id=sample_user.id,
            token="valid-token",
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )

        db_session.add_all([expired_session, valid_session])
        db_session.commit()

        now = datetime.utcnow()
        assert expired_session.expires_at < now
        assert valid_session.expires_at > now

    @pytest.mark.unit
    @pytest.mark.database
    def test_session_deactivation(self, db_session, sample_session):
        """Test session deactivation."""
        assert sample_session.is_active is True

        sample_session.is_active = False
        db_session.commit()
        db_session.refresh(sample_session)

        assert sample_session.is_active is False


class TestQueryModel:
    """Test Query model functionality."""

    @pytest.mark.unit
    @pytest.mark.database
    def test_create_query(self, db_session, sample_user):
        """Test creating a new query."""
        query = Query(
            id="test-query-new",
            user_id=sample_user.id,
            query_text="SELECT COUNT(*) FROM users",
            params={"filter": "active"},
            execution_time=250
        )
        db_session.add(query)
        db_session.commit()
        db_session.refresh(query)

        assert query.id == "test-query-new"
        assert query.user_id == sample_user.id
        assert query.query_text == "SELECT COUNT(*) FROM users"
        assert query.params == {"filter": "active"}
        assert query.execution_time == 250
        assert isinstance(query.created_at, datetime)

    @pytest.mark.unit
    @pytest.mark.database
    def test_query_json_params(self, db_session, sample_user):
        """Test storing and retrieving JSON parameters."""
        complex_params = {
            "filters": [
                {"field": "created_at", "operator": ">=", "value": "2024-01-01"},
                {"field": "status", "operator": "in", "value": ["active", "pending"]}
            ],
            "sort": {"field": "username", "order": "asc"},
            "pagination": {"page": 1, "limit": 50}
        }

        query = Query(
            id="test-query-json",
            user_id=sample_user.id,
            query_text="SELECT * FROM users WHERE status IN (?, ?)",
            params=complex_params,
            execution_time=300
        )
        db_session.add(query)
        db_session.commit()
        db_session.refresh(query)

        assert query.params == complex_params
        assert query.params["filters"][0]["field"] == "created_at"
        assert query.params["sort"]["order"] == "asc"

    @pytest.mark.unit
    @pytest.mark.database
    def test_query_performance_tracking(self, db_session, sample_user):
        """Test query execution time tracking."""
        fast_query = Query(
            id="fast-query",
            user_id=sample_user.id,
            query_text="SELECT 1",
            execution_time=10
        )

        slow_query = Query(
            id="slow-query",
            user_id=sample_user.id,
            query_text="SELECT * FROM large_table",
            execution_time=5000
        )

        db_session.add_all([fast_query, slow_query])
        db_session.commit()

        # Query for performance analysis
        all_queries = db_session.query(Query).filter(
            Query.user_id == sample_user.id
        ).all()

        execution_times = [q.execution_time for q in all_queries if q.execution_time]
        avg_execution_time = sum(execution_times) / len(execution_times)

        assert len(execution_times) >= 2
        assert min(execution_times) == 10
        assert max(execution_times) == 5000

    @pytest.mark.unit
    @pytest.mark.database
    def test_query_user_relationship(self, db_session, sample_query):
        """Test query-user relationship."""
        db_session.refresh(sample_query)

        # Access user through relationship
        user = sample_query.user
        assert user is not None
        assert user.id == sample_query.user_id


class TestReportModel:
    """Test Report model functionality."""

    @pytest.mark.unit
    @pytest.mark.database
    def test_create_report(self, db_session, sample_user):
        """Test creating a new report."""
        report_data = {
            "visualizations": [
                {
                    "type": "bar_chart",
                    "title": "Sales by Region",
                    "data": [
                        {"region": "North", "sales": 10000},
                        {"region": "South", "sales": 15000}
                    ]
                }
            ],
            "filters": {"date_range": "2024-01-01 to 2024-12-31"},
            "metadata": {"generated_at": "2024-01-15T10:30:00Z"}
        }

        report = Report(
            id="test-report-new",
            user_id=sample_user.id,
            title="Sales Analysis Report",
            description="Quarterly sales performance analysis",
            data=report_data
        )
        db_session.add(report)
        db_session.commit()
        db_session.refresh(report)

        assert report.id == "test-report-new"
        assert report.title == "Sales Analysis Report"
        assert report.description == "Quarterly sales performance analysis"
        assert report.data == report_data
        assert isinstance(report.created_at, datetime)

    @pytest.mark.unit
    @pytest.mark.database
    def test_report_complex_data_structure(self, db_session, sample_user):
        """Test storing complex data structures in report."""
        complex_data = {
            "dashboard": {
                "title": "Executive Dashboard",
                "layout": {
                    "rows": 3,
                    "columns": 2,
                    "widgets": [
                        {
                            "id": "widget-1",
                            "type": "metric",
                            "position": {"row": 0, "col": 0},
                            "config": {
                                "title": "Total Revenue",
                                "value": 1500000,
                                "format": "currency",
                                "comparison": {"previous": 1200000, "change": 0.25}
                            }
                        },
                        {
                            "id": "widget-2",
                            "type": "chart",
                            "position": {"row": 0, "col": 1},
                            "config": {
                                "chart_type": "line",
                                "title": "Monthly Growth",
                                "series": [
                                    {
                                        "name": "Revenue",
                                        "data": [100, 120, 110, 140, 150, 160, 180, 170, 190, 200, 210, 250]
                                    }
                                ]
                            }
                        }
                    ]
                }
            }
        }

        report = Report(
            id="complex-report",
            user_id=sample_user.id,
            title="Executive Dashboard Report",
            data=complex_data
        )
        db_session.add(report)
        db_session.commit()
        db_session.refresh(report)

        assert report.data["dashboard"]["title"] == "Executive Dashboard"
        assert len(report.data["dashboard"]["layout"]["widgets"]) == 2
        assert report.data["dashboard"]["layout"]["widgets"][0]["config"]["value"] == 1500000

    @pytest.mark.unit
    @pytest.mark.database
    def test_report_optional_description(self, db_session, sample_user):
        """Test creating report without description."""
        report = Report(
            id="no-description-report",
            user_id=sample_user.id,
            title="Simple Report",
            data={"simple": "data"}
        )
        db_session.add(report)
        db_session.commit()
        db_session.refresh(report)

        assert report.description is None
        assert report.title == "Simple Report"
        assert report.data == {"simple": "data"}


class TestInsightModel:
    """Test Insight model functionality."""

    @pytest.mark.unit
    @pytest.mark.database
    def test_create_insight(self, db_session, sample_query):
        """Test creating a new insight."""
        insight_details = {
            "message": "Query performance has degraded by 30% over the last week",
            "confidence": 0.92,
            "severity": "medium",
            "category": "performance_degradation",
            "affected_queries": [sample_query.id],
            "recommendations": [
                "Consider adding an index on the user_id column",
                "Review query execution plan for optimization opportunities"
            ],
            "metrics": {
                "current_avg_time": 2.5,
                "previous_avg_time": 1.9,
                "degradation_percentage": 0.31
            }
        }

        insight = Insight(
            id="test-insight-new",
            query_id=sample_query.id,
            type="performance",
            details=insight_details
        )
        db_session.add(insight)
        db_session.commit()
        db_session.refresh(insight)

        assert insight.id == "test-insight-new"
        assert insight.query_id == sample_query.id
        assert insight.type == "performance"
        assert insight.details == insight_details
        assert isinstance(insight.created_at, datetime)

    @pytest.mark.unit
    @pytest.mark.database
    def test_insight_types(self, db_session, sample_query):
        """Test different insight types."""
        insight_types = [
            "performance",
            "optimization",
            "anomaly",
            "trend",
            "security",
            "usage"
        ]

        insights = []
        for i, insight_type in enumerate(insight_types):
            insight = Insight(
                id=f"insight-{insight_type}-{i}",
                query_id=sample_query.id,
                type=insight_type,
                details={
                    "message": f"This is a {insight_type} insight",
                    "confidence": 0.8
                }
            )
            insights.append(insight)
            db_session.add(insight)

        db_session.commit()

        for insight in insights:
            db_session.refresh(insight)

        # Verify all insight types were created
        all_insights = db_session.query(Insight).filter(
            Insight.query_id == sample_query.id
        ).all()

        insight_types_created = {insight.type for insight in all_insights}
        assert insight_types_created == set(insight_types)

    @pytest.mark.unit
    @pytest.mark.database
    def test_global_insight_without_query(self, db_session):
        """Test creating system-wide insight not tied to specific query."""
        global_insight = Insight(
            id="global-insight-1",
            query_id=None,  # Global insight
            type="system",
            details={
                "message": "System-wide performance alert: Database connection pool is near capacity",
                "confidence": 0.95,
                "severity": "high",
                "system_metrics": {
                    "current_connections": 18,
                    "max_connections": 20,
                    "utilization": 0.9
                },
                "recommendations": [
                    "Consider increasing connection pool size",
                    "Review long-running queries that may be holding connections"
                ]
            }
        )
        db_session.add(global_insight)
        db_session.commit()
        db_session.refresh(global_insight)

        assert global_insight.query_id is None
        assert global_insight.type == "system"
        assert global_insight.details["confidence"] == 0.95

    @pytest.mark.unit
    @pytest.mark.database
    def test_insight_with_complex_recommendations(self, db_session, sample_query):
        """Test insight with complex recommendation structure."""
        complex_details = {
            "analysis": {
                "type": "query_optimization",
                "findings": [
                    {
                        "issue": "Missing index",
                        "table": "users",
                        "column": "email",
                        "impact": "high",
                        "estimated_improvement": "60% faster queries"
                    },
                    {
                        "issue": "Inefficient join",
                        "tables": ["users", "orders"],
                        "impact": "medium",
                        "estimated_improvement": "25% faster queries"
                    }
                ]
            },
            "recommendations": [
                {
                    "priority": 1,
                    "action": "create_index",
                    "details": {
                        "table": "users",
                        "columns": ["email"],
                        "type": "btree"
                    },
                    "estimated_effort": "5 minutes",
                    "estimated_impact": "high"
                },
                {
                    "priority": 2,
                    "action": "optimize_join",
                    "details": {
                        "current": "SELECT * FROM users u LEFT JOIN orders o ON u.id = o.user_id",
                        "optimized": "SELECT u.id, u.email, COUNT(o.id) FROM users u LEFT JOIN orders o ON u.id = o.user_id GROUP BY u.id"
                    },
                    "estimated_effort": "15 minutes",
                    "estimated_impact": "medium"
                }
            ]
        }

        insight = Insight(
            id="complex-insight",
            query_id=sample_query.id,
            type="optimization",
            details=complex_details
        )
        db_session.add(insight)
        db_session.commit()
        db_session.refresh(insight)

        assert len(insight.details["analysis"]["findings"]) == 2
        assert len(insight.details["recommendations"]) == 2
        assert insight.details["recommendations"][0]["priority"] == 1