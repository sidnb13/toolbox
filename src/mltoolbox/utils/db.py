from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    create_engine,
    func,
    or_,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    container_name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())  # noqa: DTZ005
    remotes: Mapped[list[Remote]] = relationship(
        "Remote", secondary="remote_projects", back_populates="projects",
    )
    conda_env: Mapped[str | None] = mapped_column(String, nullable=True)

# Association table for many-to-many relationship
remote_projects = Table(
    "remote_projects",
    Base.metadata,
    Column("remote_id", Integer, ForeignKey("remotes.id")),
    Column("project_id", Integer, ForeignKey("projects.id")),
)


class Remote(Base):
    __tablename__ = "remotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    alias: Mapped[str] = mapped_column(String, unique=True)
    username: Mapped[str] = mapped_column(String)
    host: Mapped[str] = mapped_column(String)
    git_name: Mapped[str] = mapped_column(String)
    last_used: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())
    projects: Mapped[list[Project]] = relationship(
        Project, secondary=remote_projects, back_populates="remotes",
    )


class DB:
    def __init__(self) -> None:
        config_dir = Path.home() / ".config" / "mltoolbox"
        config_dir.mkdir(parents=True, exist_ok=True)
        db_file = config_dir / "mltoolbox.db"

        if db_file.exists():
            try:
                self.engine = create_engine(f"sqlite:///{db_file}")
                with Session(self.engine) as session:
                    session.query(Remote).first()
            except Exception:  # noqa: BLE001
                db_file.unlink()

        self.engine = create_engine(f"sqlite:///{db_file}")
        Base.metadata.create_all(self.engine)

        self.cleanup_duplicates()

    @contextmanager
    def get_session(self):
        """Provide a transactional scope around a series of operations."""
        session = Session(self.engine)
        try:
            yield session
            session.commit()
        except:
            session.rollback()
            raise
        finally:
            session.close()

    def upsert_remote(
            self,
            username: str,
            host: str,
            project_name: str,
            container_name: str | None = None,
            conda_env: str | None = None,
            alias: str | None = None,
            *,
            update_timestamp: bool = True,
        ) -> Remote:
        """Create or update a remote entry and associate it with a project.

        Also handles updating last_used timestamp and project associations.
        """
        git_name = os.getenv("GIT_NAME")
        container_name = container_name or project_name

        def _generate_alias(session: Session) -> str:
            while True:
                max_alias = (
                    session.query(func.max(Remote.alias))
                    .filter(Remote.alias.like(f"{project_name}-%"))
                    .filter(Remote.alias.regexp_match(rf"{project_name}-\d+$"))
                    .scalar()
                )

                alias_num = 1 if not max_alias else int(max_alias.split("-")[1]) + 1
                alias = f"mltoolbox-{alias_num}"

                try:
                    session.flush()
                    return alias
                except IntegrityError:
                    session.rollback()

        with Session(self.engine) as session:
            if not alias:
                alias = _generate_alias(session)

            remote = (
                session.query(Remote)
                .filter(
                    or_(
                        Remote.alias == alias,
                        (Remote.host == host and Remote.username == username),
                    ),
                )
                .first()
            )

            project = session.query(Project).filter_by(name=project_name).first()
            if not project:
                project = Project(
                    name=project_name,
                    container_name=container_name,
                    conda_env=conda_env,
                )
                session.add(project)
            else:
                project.container_name = container_name
                if conda_env:
                    project.conda_env = conda_env

            if not remote:
                remote = Remote(
                    alias=alias,
                    username=username,
                    host=host,
                    git_name=git_name,
                )
                session.add(remote)
            else:
                remote.username = username
                remote.host = host
                remote.git_name = git_name

            if update_timestamp:
                remote.last_used = datetime.now()

            if project not in remote.projects:
                remote.projects.append(project)

            session.commit()
            session.refresh(remote)
            return remote

    def cleanup_duplicates(self):
        """Remove duplicate remote entries that have the same host, username, and project_dir."""
        with Session(self.engine) as session:
            # Find all duplicates based on unique combination of fields
            subquery = (
                session.query(
                    Remote.host,
                    Remote.username,
                    func.min(Remote.created_at).label("min_created"),
                )
                .group_by(Remote.host, Remote.username)
                .having(func.count("*") > 1)
                .subquery()
            )

            # Delete all duplicates except the oldest one
            duplicates = (
                session.query(Remote)
                .join(
                    subquery,
                    (Remote.host == subquery.c.host)
                    & (Remote.username == subquery.c.username)
                    & (Remote.created_at != subquery.c.min_created),
                )
                .all()
            )
            for duplicate in duplicates:
                session.delete(duplicate)
            session.commit()

    def delete_remote(
        self,
        host_or_alias: str | None = None,
    ) -> bool:
        with Session(self.engine) as session:
            # Query the remote within this session
            remote = (
                session.query(Remote)
                .filter(
                    or_(
                        Remote.alias.ilike(f"%{host_or_alias}%"),
                        Remote.host.ilike(f"%{host_or_alias}%"),
                    ),
                )
                .first()
            )

            if not remote:
                return False

            # Remove all project associations but don't delete the projects
            remote.projects = []

            # Delete remote entry
            session.delete(remote)

            # Clean up orphaned projects
            orphaned_projects = (
                session.query(Project)
                .filter(~Project.remotes.any())
                .all()
            )
            for project in orphaned_projects:
                session.delete(project)

            session.commit()

        return True

    def get_remote_fuzzy(self, query: str) -> Optional[Remote]:
        with Session(self.engine) as session:
            # Search in both alias and host fields
            return (
                session.query(Remote)
                .filter(
                    or_(
                        Remote.alias.ilike(f"%{query}%"),
                        Remote.host.ilike(f"%{query}%"),
                    ),
                )
                .first()
            )

    def get_remotes(self) -> list[Remote]:
        with Session(self.engine) as session:
            return session.query(Remote).all()

    def get_or_create_project(self, name: str, container_name: str) -> Project:
        with Session(self.engine) as session:
            project = session.query(Project).filter_by(name=name).first()
            if not project:
                project = Project(name=name, container_name=container_name)
                session.add(project)
                session.commit()
            return project

    def get_project(self, name: str) -> Project | None:
        with Session(self.engine) as session:
            return session.query(Project).filter_by(name=name).first()

    def list_projects(self) -> list[Project]:
        with Session(self.engine) as session:
            return session.query(Project).all()
