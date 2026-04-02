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

# --- REQUEST MODELS ---
class PromptRequest(BaseModel):
    base_text: str
    platform: str = "General"
    image_base64: Optional[str] = None  # NEW: Expect an optional image string

class ManualPostRequest(BaseModel):
    platform: str
    title: str
    description: str
    hashtags: List[str]

class UpdatePostRequest(BaseModel):
    title: str
    description: str
    hashtags: List[str]
    short_text: str  # NEW: Allow frontend to update the short version

# --- HELPER: AUTO-SUMMARIZER ---
def generate_short_version(title: str, description: str, hashtags: List[str]) -> str:
    """Uses AI to condense the post for X/Bluesky. Falls back to slicing if AI fails."""
    tags_str = " ".join([f"#{t}" for t in hashtags]) if hashtags else ""
    full_fallback = f"{title}\n\n{description}\n\n{tags_str}"
    
    # If it's already under 280, don't waste AI tokens!
    if len(full_fallback) <= 280:
        return full_fallback

    prompt = f"""
    Rewrite the following social media post to be strictly between 200-280 characters for Twitter/Bluesky.
    Tone: Human, witty, slightly humorous, and engaging. 
    Format: Use a catchy hook, a brief summary, and 1-3 key hashtags.
    
    Title: {title}
    Description: {description}
    Hashtags: {tags_str}
    """
    
    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            max_tokens=100,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"AI Shortening failed, using slice fallback: {e}")
        # HARD FALLBACK: Slice the description to fit exactly 280 chars
        available_space = 280 - len(title) - len(tags_str) - 10 
        truncated_desc = description[:max(0, available_space)] + "..."
        return f"{title}\n\n{truncated_desc}\n\n{tags_str}"

# --- ROUTES ---
@router.put("/posts/{post_id}")
async def update_post(post_id: int, request: UpdatePostRequest):
    """Updates the main text AND the short text of a saved post."""
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor()
        update_query = """
        UPDATE posts 
        SET enhanced_title = %s, enhanced_description = %s, hashtags = %s, short_text = %s
        WHERE id = %s RETURNING id;
        """
        cursor.execute(update_query, (
            request.title, 
            request.description, 
            request.hashtags,
            request.short_text, # Save manual short text edits
            post_id
        ))
        updated = cursor.fetchone()
        conn.commit()
        if not updated: raise HTTPException(status_code=404, detail="Post not found")
        return {"message": "Post updated successfully"}
    finally:
        cursor.close(); conn.close()


@router.post("/posts")
async def create_manual_post(request: ManualPostRequest):
    """Saves a manual post and automatically generates its short version."""
    short_text = generate_short_version(request.title, request.description, request.hashtags)
    
    conn = get_db_connection()
    if not conn: raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor()
        insert_query = """
        INSERT INTO posts (platform, original_prompt, enhanced_title, enhanced_description, hashtags, short_text)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id;
        """
        cursor.execute(insert_query, (
            request.platform,
            "Manual Entry", 
            request.title,
            request.description,
            request.hashtags,
            short_text
        ))
        post_id = cursor.fetchone()['id']
        conn.commit()
        return {"message": "Post saved manually", "id": post_id}
    finally:
        cursor.close(); conn.close()
        

@router.post("/enhance")
async def enhance_post(request: PromptRequest):
    """Enhances text with AI, analyzing images for context if provided."""
    
    system_prompt = f"""
    You are an expert social media manager. Your job is to enhance the provided text for {request.platform}.
    If an image is provided, analyze its contents, vibe, and details, and weave that context naturally into the post.
    Rules:
    1. DO NOT add any new facts that aren't supported by the text or image.
    2. MUST output strictly as a valid JSON object with keys: 'title', 'description', and 'hashtags'.
    3. 'hashtags' should be a list of strings.
    """
    
    try:
        # 🔥 SMART VISION LOGIC: Switch models and payload format if an image exists
        if request.image_base64:
            # UPGRADED: Using Groq's new Llama 4 Scout Vision Model
            model_to_use = "meta-llama/llama-4-scout-17b-16e-instruct" 
            user_content = [
                {"type": "text", "text": f"Enhance this text based on the attached image: {request.base_text}"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{request.image_base64}"}}
            ]
        else:
            model_to_use = "llama-3.1-8b-instant" # Standard lightning-fast text model
            user_content = f"Enhance this text: {request.base_text}"

        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            model=model_to_use,
            temperature=0.4, # Slightly higher to allow creative image interpretation
            response_format={"type": "json_object"}
        )
        
        enhanced_content = json.loads(response.choices[0].message.content)
        
        # Automatically create the short version
        short_text = generate_short_version(
            enhanced_content.get('title', ''), 
            enhanced_content.get('description', ''), 
            enhanced_content.get('hashtags', [])
        )
        
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            insert_query = """
            INSERT INTO posts (platform, original_prompt, enhanced_title, enhanced_description, hashtags, short_text)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id;
            """
            cursor.execute(insert_query, (
                request.platform,
                request.base_text,
                enhanced_content.get('title'),
                enhanced_content.get('description'),
                enhanced_content.get('hashtags'),
                short_text
            ))
            post_id = cursor.fetchone()['id']
            conn.commit()
            cursor.close()
            conn.close()
            
            enhanced_content['db_id'] = post_id
            
        return enhanced_content
    except Exception as e:
        # 🔥 This will print the EXACT Groq error to your backend terminal
        print(f"Groq API Error: {str(e)}") 
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