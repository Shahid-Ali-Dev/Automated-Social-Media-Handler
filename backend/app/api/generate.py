import os
from typing import List, Optional
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from groq import Groq
from dotenv import load_dotenv
from app.core.db import get_db_connection

load_dotenv()

router = APIRouter()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

class PromptRequest(BaseModel):
    base_text: str
    platform: str = "General"
class ManualPostRequest(BaseModel):
    platform: str
    title: str
    description: str
    hashtags: List[str]

class UpdatePostRequest(BaseModel):
    title: str
    description: str
    hashtags: List[str]

# 1. Route for updating an existing post
@router.put("/posts/{post_id}")
async def update_post(post_id: int, request: UpdatePostRequest):
    """Updates the text content of a saved post."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor()
        update_query = """
        UPDATE posts 
        SET enhanced_title = %s, enhanced_description = %s, hashtags = %s 
        WHERE id = %s RETURNING id;
        """
        cursor.execute(update_query, (
            request.title, 
            request.description, 
            request.hashtags, 
            post_id
        ))
        updated = cursor.fetchone()
        conn.commit()
        
        if not updated:
            raise HTTPException(status_code=404, detail="Post not found")
        return {"message": "Post updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

# 2. Route for manually saving a post without AI
@router.post("/posts")
async def create_manual_post(request: ManualPostRequest):
    """Saves a post directly to the database without Groq AI enhancement."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor()
        insert_query = """
        INSERT INTO posts (platform, original_prompt, enhanced_title, enhanced_description, hashtags)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id;
        """
        cursor.execute(insert_query, (
            request.platform,
            "Manual Entry", # No original prompt since it wasn't AI generated
            request.title,
            request.description,
            request.hashtags
        ))
        post_id = cursor.fetchone()['id']
        conn.commit()
        return {"message": "Post saved manually", "id": post_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
        
@router.post("/enhance")
async def enhance_post(request: PromptRequest):
    system_prompt = f"""
    You are an expert social media manager. Your job is to enhance the provided text for {request.platform}.
    Rules:
    1. DO NOT add any new facts, claims, or external information. Only enhance the style, grammar, and engagement.
    2. You MUST output your response strictly as a valid JSON object with exactly these three keys: 'title', 'description', and 'hashtags'.
    3. 'hashtags' should be a list of strings.
    """

    try:
        # 1. Generate content with Groq
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Enhance this text: {request.base_text}"}
            ],
            model="llama-3.1-8b-instant",
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        
        enhanced_content = json.loads(response.choices[0].message.content)
        
        # 2. Save to Neon Database
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            insert_query = """
            INSERT INTO posts (platform, original_prompt, enhanced_title, enhanced_description, hashtags)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
            """
            cursor.execute(insert_query, (
                request.platform,
                request.base_text,
                enhanced_content.get('title'),
                enhanced_content.get('description'),
                enhanced_content.get('hashtags')
            ))
            post_id = cursor.fetchone()['id']
            conn.commit()
            cursor.close()
            conn.close()
            
            # Attach the database ID to the response
            enhanced_content['db_id'] = post_id
            
        return enhanced_content

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/history")
async def get_history():
    """Fetches all past generations from the database, newest first."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor()
        # Fetch all posts, ordered by newest
        fetch_query = """
        SELECT p.*, 
               COALESCE(
                   json_agg(
                       json_build_object('id', m.id, 'url', m.media_url)
                   ) FILTER (WHERE m.id IS NOT NULL), '[]'
               ) as media_files
        FROM posts p
        LEFT JOIN post_media m ON p.id = m.post_id
        GROUP BY p.id
        ORDER BY p.created_at DESC;
        """
        cursor.execute(fetch_query)
        posts = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Convert datetime objects to strings so JSON can read them
        for post in posts:
            if post.get('created_at'):
                post['created_at'] = post['created_at'].isoformat()
                
        return {"posts": posts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/history/{post_id}")
async def delete_history(post_id: int):
    """Deletes a specific generation by its ID."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor()
        # Delete the row and return the ID to confirm it worked
        cursor.execute("DELETE FROM posts WHERE id = %s RETURNING id;", (post_id,))
        deleted_row = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        
        if not deleted_row:
            raise HTTPException(status_code=404, detail="Post not found")
            
        return {"message": "Post deleted successfully", "id": post_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))