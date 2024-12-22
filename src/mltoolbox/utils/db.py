import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, String, create_engine, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class Remote(Base):
    __tablename__ = "remotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    alias: Mapped[str] = mapped_column(String, unique=True)
    username: Mapped[str] = mapped_column(String)
    host: Mapped[str] = mapped_column(String)
    project_dir: Mapped[str] = mapped_column(String)
    git_name: Mapped[str] = mapped_column(String)
    container_name: Mapped[str] = mapped_column(String)
    is_conda: Mapped[bool] = mapped_column(Boolean, default=False)
    conda_env: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_used: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())


class DB:
    def __init__(self):
        config_dir = Path.home() / ".config" / "mltoolbox"
        config_dir.mkdir(parents=True, exist_ok=True)
        db_file = config_dir / "mltoolbox.db"

        if db_file.exists():
            try:
                self.engine = create_engine(f"sqlite:///{db_file}")
                with Session(self.engine) as session:
                    session.query(Remote).first()
            except Exception as e:
                db_file.unlink()

        self.engine = create_engine(f"sqlite:///{db_file}")
        Base.metadata.create_all(self.engine)

        self.cleanup_duplicates()

    def cleanup_duplicates(self):
        """Remove duplicate remote entries that have the same host, username, and project_dir."""
        with Session(self.engine) as session:
            # Find all duplicates based on unique combination of fields
            subquery = (
                session.query(
                    Remote.host,
                    Remote.username,
                    Remote.project_dir,
                    func.min(Remote.created_at).label("min_created"),
                )
                .group_by(Remote.host, Remote.username, Remote.project_dir)
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
                    & (Remote.project_dir == subquery.c.project_dir)
                    & (Remote.created_at != subquery.c.min_created),
                )
                .all()
            )
            for duplicate in duplicates:
                session.delete(duplicate)
            session.commit()

    def add_remote(
        self,
        username: str,
        host: str,
        alias: Optional[str] = None,
        is_conda: bool = False,
        conda_env: Optional[str] = None,
    ) -> Remote:
        project_dir = str(Path.cwd())
        git_name = os.getenv("GIT_NAME")
        container_name = os.getenv("PROJECT_NAME", Path.cwd().name)

        if not alias:
            with Session(self.engine) as session:
                while True:
                    # Lock the table to prevent concurrent reads
                    max_alias = (
                        session.query(func.max(Remote.alias))
                        .filter(Remote.alias.like("mltoolbox-%"))
                        .filter(Remote.alias.regexp_match(r"mltoolbox-\d+$"))
                        .scalar()
                    )

                    if not max_alias:
                        alias = "mltoolbox-1"
                    else:
                        current_num = int(max_alias.split("-")[1])
                        alias = f"mltoolbox-{current_num + 1}"

                    try:
                        # Try to insert with the new alias - if it fails due to duplicate,
                        # the transaction will rollback and we'll try again
                        session.flush()
                        break
                    except IntegrityError:
                        session.rollback()
                        continue

        with Session(self.engine) as session:
            remote = session.query(Remote).filter_by(alias=alias).first()
            if remote is None:
                remote = Remote(
                    alias=alias,
                    username=username,
                    host=host,
                    project_dir=project_dir,
                    git_name=git_name,
                    container_name=container_name,
                    is_conda=is_conda,
                    conda_env=conda_env,
                )
                session.add(remote)
            else:
                remote.username = username
                remote.host = host
                remote.project_dir = project_dir
                remote.git_name = git_name
                remote.container_name = container_name
                remote.is_conda = is_conda
                remote.conda_env = conda_env
                remote.last_used = datetime.now()

            session.commit()

            session.refresh(remote)
            return remote

    def get_remote(
        self,
        alias: Optional[str] = None,
        host: Optional[str] = None,
        username: Optional[str] = None,
    ) -> Optional[Remote]:
        with Session(self.engine) as session:
            filters = {}
            if alias:
                filters["alias"] = alias
            if host:
                filters["host"] = host
            if username:
                filters["username"] = username

            return session.query(Remote).filter_by(**filters).first()

    def get_remotes(self) -> List[Remote]:
        with Session(self.engine) as session:
            return session.query(Remote).all()

    def delete_remote(
        self,
        alias: Optional[str] = None,
        host: Optional[str] = None,
        username: Optional[str] = None,
    ) -> None:
        with Session(self.engine) as session:
            filters = {}
            if alias:
                filters["alias"] = alias
            if host:
                filters["host"] = host
            if username:
                filters["username"] = username

            remote = session.query(Remote).filter_by(**filters).first()
            session.delete(remote)
            session.commit()

    def update_last_used(
        self,
        alias: Optional[str] = None,
        host: Optional[str] = None,
        username: Optional[str] = None,
    ) -> None:
        with Session(self.engine) as session:
            filters = {}
            if alias:
                filters["alias"] = alias
            if host:
                filters["host"] = host
            if username:
                filters["username"] = username

            remote = session.query(Remote).filter_by(**filters).first()

            remote.last_used = datetime.now()
            session.commit()
