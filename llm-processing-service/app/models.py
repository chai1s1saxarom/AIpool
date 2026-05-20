from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON
from sqlalchemy.sql import func
from app.database import Base


class LLMJob(Base):
    __tablename__ = "llm_jobs"

    job_id = Column(String, primary_key=True, index=True)
    user_request_id = Column(String, nullable=False, index=True)
    llm_model_id = Column(String, nullable=False)
    consumer_service_id = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending/processing/done/failed/cancelled
    messages = Column(JSON, nullable=False)
    webhook_url = Column(String, nullable=True)
    timeout = Column(Integer, default=120)
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=4000)
    structured_output = Column(Boolean, default=False)

    # Результат
    result_response = Column(Text, nullable=True)
    result_input_tokens = Column(Integer, nullable=True)
    result_output_tokens = Column(Integer, nullable=True)
    result_total_cost_usd = Column(Float, nullable=True)

    error_message = Column(Text, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
