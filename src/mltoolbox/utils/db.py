import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class Remote(Base):
    __tablename__ = "remotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    alias: Mapped[str] = mapped_column(String, unique=True)
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

        self.engine = create_engine(f"sqlite:///{config_dir}/mltoolbox.db")
        Base.metadata.create_all(self.engine)

    def add_remote(
        self,
        host: str,
        alias: Optional[str] = None,
        is_conda: bool = False,
        conda_env: Optional[str] = None,
    ) -> Remote:
        project_dir = str(Path.cwd())
        git_name = os.getenv("GIT_NAME")
        container_name = os.getenv("CONTAINER_NAME", Path.cwd().name)

        if not alias:
            alias = host

        with Session(self.engine) as session:
            remote = session.query(Remote).filter_by(alias=alias).first()
            if remote is None:
                remote = Remote(
                    alias=alias,
                    host=host,
                    project_dir=project_dir,
                    git_name=git_name,
                    container_name=container_name,
                    is_conda=is_conda,
                    conda_env=conda_env,
                )
                session.add(remote)
            else:
                remote.host = host
                remote.project_dir = project_dir
                remote.git_name = git_name
                remote.container_name = container_name
                remote.is_conda = is_conda
                remote.conda_env = conda_env
                remote.last_used = datetime.now()

            session.commit()

            return remote

    def get_remote(self, alias: str) -> Remote:
        with Session(self.engine) as session:
            remote = session.query(Remote).filter_by(alias=alias).first()
            return remote

    def get_remotes(self) -> List[Remote]:
        with Session(self.engine) as session:
            return session.query(Remote).all()

    def delete_remote(self, alias: str) -> None:
        with Session(self.engine) as session:
            remote = session.query(Remote).filter_by(alias=alias).first()
            if remote is None:
                raise ValueError(f"Remote {alias} not found")

            session.delete(remote)
            session.commit()

    def update_last_used(self, alias: str) -> None:
        with Session(self.engine) as session:
            remote = session.query(Remote).filter_by(alias=alias).first()
            if remote is None:
                raise ValueError(f"Remote {alias} not found")

            remote.last_used = datetime.now()
            session.commit()
