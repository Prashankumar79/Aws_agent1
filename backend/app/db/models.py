from sqlalchemy import Column, String, DateTime, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Job(Base):
    """Job model for tracking background tasks"""
    __tablename__ = "jobs"
    
    id = Column(String, primary_key=True)
    job_type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Analysis(Base):
    """Analysis model for storing diagram analysis results"""
    __tablename__ = "analyses"
    
    id = Column(String, primary_key=True)
    file_path = Column(String, nullable=False)
    providers = Column(JSON, nullable=True)
    cloud_schema = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class DesignDoc(Base):
    """Design document model"""
    __tablename__ = "design_docs"
    
    id = Column(String, primary_key=True)
    analysis_id = Column(String, nullable=False)
    content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class TerraformCode(Base):
    """Terraform code model"""
    __tablename__ = "terraform_codes"
    
    id = Column(String, primary_key=True)
    design_id = Column(String, nullable=False)
    code = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
