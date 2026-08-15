"""
Configuration settings for AgriPinya
"""

import os

class Config:
    """Base configuration"""
    
    # Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'agripinya-secret-key-change-in-production'
    DEBUG = True
    
    # Upload settings
    UPLOAD_FOLDER = 'uploads'
    RESULTS_FOLDER = 'results'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    
    # Model settings
    MODEL_PATH = 'models/pineapple_disease_model.pt'
    IMAGE_SIZE = (640, 640)
    
    # Detection settings
    CONFIDENCE_THRESHOLD = 0.5
    
    # Database (for future use)
    DATABASE_URI = os.environ.get('DATABASE_URI') or 'sqlite:///agripinya.db'
    
    # API settings
    API_RATE_LIMIT = '100 per hour'
    
    # Logging
    LOG_LEVEL = 'INFO'
    LOG_FILE = 'agripinya.log'


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    
    # Override with environment variables in production
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
    # Use production database
    DATABASE_URI = os.environ.get('DATABASE_URI') or 'postgresql://user:pass@localhost/agripinya'


class TestingConfig(Config):
    """Testing configuration"""
    DEBUG = True
    TESTING = True
    
    # Use test database
    DATABASE_URI = 'sqlite:///test_agripinya.db'


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
