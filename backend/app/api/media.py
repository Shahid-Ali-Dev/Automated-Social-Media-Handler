# media.py
import os
from typing import List
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv
from app.core.db import get_db_connection

load_dotenv()

router = APIRouter()

cloudinary.config( 
  cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME"), 
  api_key = os.environ.get("CLOUDINARY_API_KEY"), 
  api_secret = os.environ.get("CLOUDINARY_API_SECRET"),
  secure = True
)

@router.post("/upload")
async def upload_multiple_media(
    post_id: int = Form(...),
    files: List[UploadFile] = File(...) 
):
    """Uploads multiple files to Cloudinary and links them to the post."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    uploaded_media = []
    cursor = conn.cursor()

    try:
        for file in files:
            contents = await file.read()
            # Upload to Cloudinary
            result = cloudinary.uploader.upload(
                contents, 
                folder="social_auto_engine",
                resource_type="auto" 
            )
            
            media_url = result.get("secure_url")
            public_id = result.get("public_id") # We need this to delete it later
            
            # Insert into our new post_media table
            insert_query = """
            INSERT INTO post_media (post_id, media_url, cloudinary_public_id) 
            VALUES (%s, %s, %s) RETURNING id;
            """
            cursor.execute(insert_query, (post_id, media_url, public_id))
            media_id = cursor.fetchone()['id']
            
            uploaded_media.append({"id": media_id, "url": media_url})
            
        conn.commit()
        return {"message": "Upload successful", "media": uploaded_media}
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@router.delete("/{media_id}")
async def delete_single_media(media_id: int):
    """Deletes an image from Cloudinary AND the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Get the Cloudinary public_id
        cursor.execute("SELECT cloudinary_public_id FROM post_media WHERE id = %s;", (media_id,))
        media_record = cursor.fetchone()
        
        if not media_record:
            raise HTTPException(status_code=404, detail="Media not found")
            
        public_id = media_record['cloudinary_public_id']
        
        # 2. Delete from Cloudinary
        cloudinary.uploader.destroy(public_id)
        
        # 3. Delete from Database
        cursor.execute("DELETE FROM post_media WHERE id = %s;", (media_id,))
        conn.commit()
        
        return {"message": "Media deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()