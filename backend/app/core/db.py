import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    """Establishes and returns a connection to Neon Postgres."""
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def init_db():
    """Creates the posts table if it doesn't already exist."""
    conn = get_db_connection()
    if conn is None:
        return
        
    cursor = conn.cursor()
    create_table_query = """
    CREATE TABLE IF NOT EXISTS posts (
        id SERIAL PRIMARY KEY,
        platform VARCHAR(50),
        original_prompt TEXT,
        enhanced_title TEXT,
        enhanced_description TEXT,
        hashtags TEXT[],
        media_url TEXT,
        status VARCHAR(20) DEFAULT 'Draft',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    create_media_table_query = """
    CREATE TABLE IF NOT EXISTS post_media (
        id SERIAL PRIMARY KEY,
        post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
        media_url TEXT NOT NULL,
        cloudinary_public_id TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    create_logs_table_query = """
    CREATE TABLE IF NOT EXISTS publish_logs (
        id SERIAL PRIMARY KEY,
        post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
        platform VARCHAR(50) NOT NULL,
        status VARCHAR(20) NOT NULL, -- 'Success' or 'Failed'
        error_message TEXT,
        published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    create_tokens_table_query = """
    CREATE TABLE IF NOT EXISTS api_tokens (
        platform VARCHAR(50) PRIMARY KEY,
        access_token TEXT NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    
    cursor.execute(create_tokens_table_query)
    cursor.execute(create_logs_table_query)
    cursor.execute(create_table_query)
    cursor.execute(create_media_table_query)
    cursor.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS short_text TEXT;")
    conn.commit()
    cursor.close()
    conn.close()
    print("Database initialized successfully.")