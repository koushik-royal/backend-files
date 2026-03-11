from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# This is the URL for our database file.
# It will create a new file named "eyenova.db" in your project folder.
DATABASE_URL = "sqlite:///./eyenova.db"

# This is the "engine" that SQLAlchemy uses to connect to the database.
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

# This creates a "Session" class, which we will use to interact with the database.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# This is a base class that our models will inherit from.
Base = declarative_base()