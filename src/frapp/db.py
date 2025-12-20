from sqlmodel import SQLModel, Session, create_engine

# Für Demo-Zwecke SQLite im Arbeitsverzeichnis
engine = create_engine("sqlite:///./frapp.db", echo=False)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
