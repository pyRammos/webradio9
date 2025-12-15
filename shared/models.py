from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import uuid
from .config import config

Base = declarative_base()

class Station(Base):
    __tablename__ = 'stations'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    stream_url = Column(Text, nullable=False)
    format = Column(String(50))
    bitrate = Column(Integer)
    sample_rate = Column(Integer)
    channels = Column(Integer)
    is_valid = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    recordings = relationship("Recording", back_populates="station")

class Recording(Base):
    __tablename__ = 'recordings'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    station_id = Column(Integer, ForeignKey('stations.id'), nullable=False)
    podcast_id = Column(Integer, ForeignKey('podcasts.id'), nullable=True)  # Optional podcast attachment
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    duration = Column(Integer)  # in seconds
    status = Column(String(20), default='SCHEDULED')  # SCHEDULED, RECORDING, COMPLETE, PARTIAL, FAILED
    file_path = Column(Text)
    file_size = Column(Integer)  # in bytes
    format = Column(String(10), default='mp3')
    bitrate = Column(Integer)
    is_recurring = Column(Boolean, default=False)
    recurrence_type = Column(String(20))  # DAILY, WEEKDAYS, WEEKENDS, WEEKLY
    recurrence_end = Column(DateTime, nullable=True)  # Optional end date for recurring recordings
    save_to_additional_local = Column(Boolean, default=False)
    save_to_nextcloud = Column(Boolean, default=False)
    nextcloud_base_dir = Column(String(255), default='/Recordings')  # NextCloud base directory
    local_storage_status = Column(String(20), default='PENDING')  # PENDING, SUCCESS, FAILED
    nextcloud_storage_status = Column(String(20), default='PENDING')  # PENDING, SUCCESS, FAILED
    was_interrupted = Column(Boolean, default=False)  # Track if recording was restarted
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    station = relationship("Station", back_populates="recordings")
    parts = relationship("RecordingPart", back_populates="recording")
    podcast_episodes = relationship("PodcastEpisode", back_populates="recording")

class Podcast(Base):
    __tablename__ = 'podcasts'
    
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    description = Column(Text)
    author = Column(String(255))
    email = Column(String(255))
    category = Column(String(255))
    language = Column(String(10), default='en-GB')
    image_url = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    episodes = relationship("PodcastEpisode", back_populates="podcast")

class PodcastEpisode(Base):
    __tablename__ = 'podcast_episodes'
    
    id = Column(Integer, primary_key=True)
    podcast_id = Column(Integer, ForeignKey('podcasts.id'), nullable=False)
    recording_id = Column(Integer, ForeignKey('recordings.id'), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    episode_number = Column(Integer)
    season_number = Column(Integer, default=1)
    pub_date = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    podcast = relationship("Podcast", back_populates="episodes")
    recording = relationship("Recording", back_populates="podcast_episodes")

class RecordingPart(Base):
    __tablename__ = 'recording_parts'
    
    id = Column(Integer, primary_key=True)
    recording_id = Column(Integer, ForeignKey('recordings.id'), nullable=False)
    part_number = Column(Integer, nullable=False)
    file_path = Column(Text, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    recording = relationship("Recording", back_populates="parts")

# Database setup
def get_database_url():
    return f"mysql+pymysql://{config.get('database', 'username')}:{config.get('database', 'password')}@{config.get('database', 'host')}:{config.get('database', 'port')}/{config.get('database', 'database')}"

engine = create_engine(
    get_database_url(),
    pool_size=20,  # Increased from default 5
    max_overflow=30,  # Increased from default 10
    pool_timeout=60,  # Increased timeout
    pool_recycle=3600  # Recycle connections every hour
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_tables():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
