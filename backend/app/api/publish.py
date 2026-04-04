import os
import tempfile
import praw
import requests
import base64
from atproto import Client as BskyClient
from typing import List, Optional
from pydantic import BaseModel
import time
from datetime import datetime
from pydantic import BaseModel
import tweepy
from fastapi import APIRouter, HTTPException
from app.core.db import get_db_connection
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from mastodon import Mastodon

load_dotenv()

router = APIRouter()

# ==========================================
# 1. AUTHENTICATION & CONFIGURATION
# ==========================================

# X (Twitter) Authentication
auth = tweepy.OAuth1UserHandler(
    os.environ.get("X_API_KEY"),
    os.environ.get("X_API_SECRET"),
    os.environ.get("X_ACCESS_TOKEN"),
    os.environ.get("X_ACCESS_TOKEN_SECRET")
)
api_v1 = tweepy.API(auth) # For X media uploads

client = tweepy.Client(
    consumer_key=os.environ.get("X_API_KEY"),
    consumer_secret=os.environ.get("X_API_SECRET"),
    access_token=os.environ.get("X_ACCESS_TOKEN"),
    access_token_secret=os.environ.get("X_ACCESS_TOKEN_SECRET")
) 

class UnifiedPublishRequest(BaseModel):
    platforms: List[str]
    admin_password: str
    pinterest_board_id: Optional[str] = None
    reddit_subreddit: Optional[str] = None

class SkipPublishException(Exception):
    pass
# ==========================================
# 2. HELPER UTILITIES
# ==========================================

def log_publish_attempt(post_id, platform, status, error_msg=""):
    """Saves the publish attempt (success or fail) to the database."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO publish_logs (post_id, platform, status, error_message) VALUES (%s, %s, %s, %s)",
                (post_id, platform, status, error_msg)
            )
            conn.commit()
        except Exception as e:
            print(f"Failed to log attempt: {e}")
        finally:
            cursor.close()
            conn.close()
    
def is_video(url: str) -> bool:
    """Checks if the Cloudinary URL is a video file."""
    if not url: return False
    video_extensions = ['.mp4', '.mov', '.webm', '.avi', '.mkv']
    return any(ext in url.lower() for ext in video_extensions) or "/video/upload/" in url

def format_tweet_text(title, description, hashtags):
    """Formats the post and ensures it stays under X's 280-character limit."""
    tags_str = " ".join([f"#{tag}" for tag in hashtags]) if hashtags else ""
    tweet = f"{title}\n\n{description}\n\n{tags_str}"
    
    if len(tweet) > 280:
        available_space = 280 - len(title) - len(tags_str) - 10 
        truncated_desc = description[:available_space] + "..."
        tweet = f"{title}\n\n{truncated_desc}\n\n{tags_str}"
    return tweet

def get_linkedin_user_urn(access_token):
    """Dynamically fetches the URN for the authenticated LinkedIn user."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "LinkedIn-Version": "202401" 
    }
    response = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers)
    if response.status_code == 200:
        sub_id = response.json().get("sub")
        return sub_id if sub_id.startswith("urn:li:person:") else f"urn:li:person:{sub_id}"
    raise Exception(f"Failed to fetch URN: {response.text}")

def upload_media_to_linkedin(media_url, access_token, author_urn, is_vid):
    """Downloads from Cloudinary and uploads binary to LinkedIn."""
    headers = {"Authorization": f"Bearer {access_token}", "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"}
    recipe = "urn:li:digitalmediaRecipe:feedshare-video" if is_vid else "urn:li:digitalmediaRecipe:feedshare-image"
    
    # 1. Register Upload
    reg_payload = {"registerUploadRequest": {"recipes": [recipe], "owner": author_urn, "serviceRelationships": [{"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}]}}
    reg_response = requests.post("https://api.linkedin.com/v2/assets?action=registerUpload", headers=headers, json=reg_payload)
    if reg_response.status_code != 200: raise Exception(f"Failed to register media: {reg_response.text}")
        
    upload_url = reg_response.json()['value']['uploadMechanism']['com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest']['uploadUrl']
    asset_urn = reg_response.json()['value']['asset']

    # 2. Download & Upload Binary
    media_response = requests.get(media_url)
    upload_headers = {"Authorization": f"Bearer {access_token}"}
    if is_vid: upload_headers["Content-Type"] = "application/octet-stream"
        
    upload_res = requests.put(upload_url, headers=upload_headers, data=media_response.content)
    if upload_res.status_code not in [200, 201]: raise Exception(f"Failed to upload binary: {upload_res.text}")
    return asset_urn

def get_page_access_token(system_user_token, page_id):
    """Exchanges System Token for explicit Facebook Page Token."""
    response = requests.get(f"https://graph.facebook.com/v19.0/{page_id}?fields=access_token", params={"access_token": system_user_token})
    if response.status_code == 200: return response.json().get("access_token")
    raise Exception(f"Failed to swap Page Token: {response.text}")

def optimize_media_url_for_ig(url):
    """Forces Cloudinary to pad images to 4:5 to prevent Instagram Aspect Ratio errors."""
    if url and "/upload/" in url and not is_video(url):
        return url.replace("/upload/", "/upload/c_pad,ar_4:5,b_black/")
    return url

def get_smart_threads_token():
    """Fetches the Threads token from the DB. Refreshes it silently if > 50 days old."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if we have a token in the database
    cursor.execute("SELECT access_token, updated_at FROM api_tokens WHERE platform = 'Threads';")
    record = cursor.fetchone()
    
    # If not in DB, grab the initial one from .env and save it
    if not record:
        initial_token = os.environ.get("THREADS_ACCESS_TOKEN")
        cursor.execute("INSERT INTO api_tokens (platform, access_token) VALUES ('Threads', %s);", (initial_token,))
        conn.commit()
        token_to_use = initial_token
        updated_at = datetime.now()
    else:
        token_to_use = record['access_token']
        updated_at = record['updated_at']
        
    # THE SMART REFRESH LOGIC
    days_old = (datetime.now() - updated_at).days
    
    if days_old >= 50:
        print("Threads token is 50+ days old. Initiating silent refresh...")
        refresh_url = "https://graph.threads.net/v1.0/refresh_access_token"
        params = {"grant_type": "th_refresh_token", "access_token": token_to_use}
        
        response = requests.get(refresh_url, params=params)
        if response.status_code == 200:
            new_token = response.json().get("access_token")
            # Update the DB with the new token and reset the updated_at timer to NOW
            cursor.execute("UPDATE api_tokens SET access_token = %s, updated_at = CURRENT_TIMESTAMP WHERE platform = 'Threads';", (new_token,))
            conn.commit()
            token_to_use = new_token
            print("Silent refresh successful! Timer reset to Day 0.")
        else:
            print(f"Warning: Token refresh failed: {response.text}")
            
    cursor.close()
    conn.close()
    
    return token_to_use

def get_smart_pinterest_token():
    """Fetches the Pinterest token from the DB. Refreshes it silently if >= 25 days old."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Fetch both tokens using our clever dual-row hack
    cursor.execute("SELECT access_token, updated_at FROM api_tokens WHERE platform = 'Pinterest_Access';")
    access_record = cursor.fetchone()
    
    cursor.execute("SELECT access_token FROM api_tokens WHERE platform = 'Pinterest_Refresh';")
    refresh_record = cursor.fetchone()
    
    # If not in DB, grab the initial ones from .env and save them
    if not access_record or not refresh_record:
        acc_token = os.environ.get("PINTEREST_INITIAL_ACCESS_TOKEN")
        ref_token = os.environ.get("PINTEREST_INITIAL_REFRESH_TOKEN")
        
        # Insert them safely
        cursor.execute("INSERT INTO api_tokens (platform, access_token) VALUES ('Pinterest_Access', %s) ON CONFLICT (platform) DO UPDATE SET access_token = EXCLUDED.access_token;", (acc_token,))
        cursor.execute("INSERT INTO api_tokens (platform, access_token) VALUES ('Pinterest_Refresh', %s) ON CONFLICT (platform) DO UPDATE SET access_token = EXCLUDED.access_token;", (ref_token,))
        conn.commit()
        
        token_to_use = acc_token
        refresh_to_use = ref_token
        updated_at = datetime.now()
    else:
        token_to_use = access_record['access_token']
        refresh_to_use = refresh_record['access_token']
        updated_at = access_record['updated_at']
        
    # THE SMART REFRESH LOGIC
    days_old = (datetime.now() - updated_at).days
    
    # Pinterest access tokens expire at 30 days. We refresh safely at day 25.
    if days_old >= 25:
        print("Pinterest token is 25+ days old. Initiating silent refresh...")
        
        app_id = os.environ.get("PINTEREST_APP_ID")
        app_secret = os.environ.get("PINTEREST_APP_SECRET")
        
        # Pinterest requires Basic Auth encoding for refreshes
        auth_string = f"{app_id}:{app_secret}"
        b64_auth = base64.b64encode(auth_string.encode()).decode()
        
        headers = {
            "Authorization": f"Basic {b64_auth}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_to_use
        }
        
        response = requests.post("https://api.pinterest.com/v5/oauth/token", headers=headers, data=data)
        
        if response.status_code == 200:
            new_data = response.json()
            new_acc_token = new_data.get("access_token")
            new_ref_token = new_data.get("refresh_token") # Pinterest gives us a new refresh token too!
            
            # Update the DB with the new tokens and reset the timer
            cursor.execute("UPDATE api_tokens SET access_token = %s, updated_at = CURRENT_TIMESTAMP WHERE platform = 'Pinterest_Access';", (new_acc_token,))
            if new_ref_token:
                cursor.execute("UPDATE api_tokens SET access_token = %s, updated_at = CURRENT_TIMESTAMP WHERE platform = 'Pinterest_Refresh';", (new_ref_token,))
            
            conn.commit()
            token_to_use = new_acc_token
            print("Pinterest silent refresh successful! Timer reset to Day 0.")
        else:
            print(f"Warning: Pinterest Token refresh failed: {response.text}")
            
    cursor.close()
    conn.close()
    
    return token_to_use
# ==========================================
# 3. CORE PUBLISHING LOGIC (Internal Processors)
# ==========================================

async def process_x(post_id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s LIMIT 4;", (post_id,))
        media_records = cursor.fetchall()
        
        media_ids = []
        if media_records:
            for record in media_records:
                res = requests.get(record['media_url'])
                if res.status_code == 200:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                        tmp.write(res.content)
                        tmp_path = tmp.name
                    try:
                        # V1.1 Upload (Requires Free/Basic/Pro tier)
                        media_upload = api_v1.media_upload(tmp_path)
                        media_ids.append(media_upload.media_id)
                    except Exception as media_err:
                        # If media upload fails, we should know why (e.g., "Too Many Requests" or "Forbidden")
                        raise Exception(f"X Media Upload Failed: {str(media_err)}")
                    finally:
                        if os.path.exists(tmp_path): os.remove(tmp_path)

        # Try to use the AI short text first. If it's an old post without one, fallback to the slicer.
        tweet_text = post.get('short_text') 
        if not tweet_text:
            tweet_text = format_tweet_text(post['enhanced_title'], post['enhanced_description'], post['hashtags'])

        # V2 Tweet Creation
        response = client.create_tweet(text=tweet_text, media_ids=media_ids if media_ids else None)

        # Robust check for the response
        if not response or not response.data or 'id' not in response.data:
            raise Exception("X API did not return a Tweet ID. Check if your API key permissions are set to 'Read and Write'.")

    except Exception as e:
        # 🔥 Catch EVERY error (auth, network, API) and raise it as a string
        # This ensures the Master Controller logs the EXACT failure reason
        raise Exception(str(e))
    finally:
        if conn:
            cursor.close()
            conn.close()

async def process_linkedin(post_id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s LIMIT 9;", (post_id,))
        media_records = cursor.fetchall()
            
        tags_str = " ".join([f"#{tag}" for tag in post['hashtags']]) if post['hashtags'] else ""
        full_text = f"{post['enhanced_title']}\n\n{post['enhanced_description']}\n\n{tags_str}"
        
        access_token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
        author_urn = os.environ.get("LINKEDIN_ORG_URN")
        
        linkedin_media_items = []
        is_post_video = False
        
        if media_records:
            for record in media_records:
                is_vid = is_video(record['media_url'])
                if is_vid: is_post_video = True
                asset_urn = upload_media_to_linkedin(record['media_url'], access_token, author_urn, is_vid)
                linkedin_media_items.append({"status": "READY", "description": {"text": post['enhanced_title']}, "media": asset_urn, "title": {"text": post['enhanced_title']}})

        category = "NONE" if not linkedin_media_items else ("VIDEO" if is_post_video else "IMAGE")
        share_content = {"shareCommentary": {"text": full_text}, "shareMediaCategory": category}
        if linkedin_media_items: share_content["media"] = linkedin_media_items

        payload = {"author": author_urn, "lifecycleState": "PUBLISHED", "specificContent": {"com.linkedin.ugc.ShareContent": share_content}, "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}}
        headers = {"Authorization": f"Bearer {access_token}", "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"}
        
        response = requests.post("https://api.linkedin.com/v2/ugcPosts", headers=headers, json=payload)
        if response.status_code != 201: raise Exception(f"LinkedIn API Error: {response.text}")
    finally:
        if conn: cursor.close(); conn.close()

async def process_facebook(post_id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s LIMIT 10;", (post_id,))
        media_records = cursor.fetchall()
        
        full_text = f"{post['enhanced_title']}\n\n{post['enhanced_description']}\n\n" + (" ".join([f"#{t}" for t in post['hashtags']]) if post['hashtags'] else "")
        page_token = get_page_access_token(os.environ.get("META_ACCESS_TOKEN"), os.environ.get("FACEBOOK_PAGE_ID"))
        page_id = os.environ.get("FACEBOOK_PAGE_ID")
        
        if not media_records:
            res = requests.post(f"https://graph.facebook.com/v19.0/{page_id}/feed", data={"message": full_text, "access_token": page_token})
        elif len(media_records) == 1:
            is_vid = is_video(media_records[0]['media_url'])
            url = f"https://graph.facebook.com/v19.0/{page_id}/videos" if is_vid else f"https://graph.facebook.com/v19.0/{page_id}/photos"
            payload = {"file_url" if is_vid else "url": media_records[0]['media_url'], "description" if is_vid else "message": full_text, "access_token": page_token}
            res = requests.post(url, data=payload)
        else:
            attached_media = []
            for record in media_records:
                photo_res = requests.post(f"https://graph.facebook.com/v19.0/{page_id}/photos", data={"url": record['media_url'], "published": "false", "access_token": page_token})
                if photo_res.status_code == 200: attached_media.append(photo_res.json().get("id"))
            
            payload = {"message": full_text, "access_token": page_token}
            for i, media_id in enumerate(attached_media): payload[f"attached_media[{i}]"] = f'{{"media_fbid":"{media_id}"}}'
            res = requests.post(f"https://graph.facebook.com/v19.0/{page_id}/feed", data=payload)

        if res.status_code != 200: raise Exception(f"Facebook API Error: {res.text}")
    finally:
        if conn: cursor.close(); conn.close()

async def process_instagram(post_id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        
        # Fetch media
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s LIMIT 10;", (post_id,))
        media_records = cursor.fetchall()

        if not media_records:
            raise SkipPublishException("Smart Skip: Instagram requires an image or video. No media found.")
            
        full_text = f"{post['enhanced_title']}\n\n{post['enhanced_description']}\n\n" + (" ".join([f"#{t}" for t in post['hashtags']]) if post['hashtags'] else "")
        page_token = get_page_access_token(os.environ.get("META_ACCESS_TOKEN"), os.environ.get("FACEBOOK_PAGE_ID"))
        ig_id = os.environ.get("INSTAGRAM_ACCOUNT_ID")
        
        # --- Proceed with Container Creation ---
        if len(media_records) == 1:
            safe_url = optimize_media_url_for_ig(media_records[0]['media_url'])
            is_vid = is_video(media_records[0]['media_url'])
            
            container_payload = {"caption": full_text, "access_token": page_token}
            if is_vid:
                container_payload["video_url"] = safe_url
                container_payload["media_type"] = "REELS"
            else:
                container_payload["image_url"] = safe_url
                
            # Added timeout to prevent the crash you saw on Threads
            cont_response = requests.post(f"https://graph.facebook.com/v19.0/{ig_id}/media", data=container_payload, timeout=(10, 180))
            if cont_response.status_code != 200: raise Exception(f"IG container failed: {cont_response.text}")
            creation_id = cont_response.json().get("id")
            
            if is_vid:
                for _ in range(15): 
                    time.sleep(5)
                    status_res = requests.get(f"https://graph.facebook.com/v19.0/{creation_id}?fields=status_code&access_token={page_token}")
                    if status_res.status_code == 200 and status_res.json().get('status_code') == 'FINISHED': break
        else:
            # Multi-media Carousels (Note: Carousels still use "VIDEO" inside children, 
            # but the main container handles it differently)
            children_ids = []
            for record in media_records:
                safe_url = optimize_media_url_for_ig(record['media_url'])
                is_vid = is_video(record['media_url'])
                payload = {"is_carousel_item": "true", "access_token": page_token, "video_url" if is_vid else "image_url": safe_url}
                if is_vid: payload["media_type"] = "VIDEO"
                item_res = requests.post(f"https://graph.facebook.com/v19.0/{ig_id}/media", data=payload, timeout=(10, 120))
                if item_res.status_code == 200: children_ids.append(item_res.json().get("id"))
            
            car_res = requests.post(f"https://graph.facebook.com/v19.0/{ig_id}/media", data={"media_type": "CAROUSEL", "children": ",".join(children_ids), "caption": full_text, "access_token": page_token}, timeout=(10, 120))
            creation_id = car_res.json().get("id")

        pub_response = requests.post(f"https://graph.facebook.com/v19.0/{ig_id}/media_publish", data={"creation_id": creation_id, "access_token": page_token}, timeout=(10, 120))
        if pub_response.status_code != 200: raise Exception(f"Failed to publish to IG: {pub_response.text}")
    finally:
        if conn: cursor.close(); conn.close()

async def process_threads(post_id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s LIMIT 10;", (post_id,))
        media_records = cursor.fetchall()
            
        full_text = f"{post['enhanced_title']}\n\n{post['enhanced_description']}\n\n" + (" ".join([f"#{t}" for t in post['hashtags']]) if post['hashtags'] else "")
        
        threads_token = get_smart_threads_token()
        threads_id = "me" 
        
        # --- STEP 1: CREATE CONTAINER ---
        
        # A. TEXT ONLY POST
        if not media_records:
            payload = {"media_type": "TEXT", "text": full_text, "access_token": threads_token}
            res = requests.post(f"https://graph.threads.net/v1.0/{threads_id}/threads", data=payload, timeout=(10, 60))
            if not res.ok: raise Exception(f"Threads Text Container Error: {res.text}")
            creation_id = res.json().get("id")
            
        # B. SINGLE IMAGE OR VIDEO
        elif len(media_records) == 1:
            is_vid = is_video(media_records[0]['media_url'])
            payload = {"text": full_text, "access_token": threads_token}
            
            if is_vid:
                payload["media_type"] = "VIDEO"
                payload["video_url"] = media_records[0]['media_url']
            else:
                payload["media_type"] = "IMAGE"
                payload["image_url"] = media_records[0]['media_url']
                
            res = requests.post(f"https://graph.threads.net/v1.0/{threads_id}/threads", data=payload, timeout=(10, 180))
            if not res.ok: raise Exception(f"Threads Media Container Error: {res.text}")
            creation_id = res.json().get("id")
            
            # Wait for video processing
            if is_vid:
                for _ in range(15): 
                    time.sleep(5)
                    status_res = requests.get(f"https://graph.threads.net/v1.0/{creation_id}?fields=status&access_token={threads_token}")
                    if status_res.status_code == 200 and status_res.json().get('status') == 'FINISHED': break
                    
        # C. CAROUSEL (MULTI-IMAGE/VIDEO)
        else:
            children_ids = []
            for record in media_records:
                is_vid = is_video(record['media_url'])
                payload = {"is_carousel_item": "true", "access_token": threads_token}
                if is_vid:
                    payload["media_type"] = "VIDEO"
                    payload["video_url"] = record['media_url']
                else:
                    payload["media_type"] = "IMAGE"
                    payload["image_url"] = record['media_url']
                
                # Upload individual item
                item_res = requests.post(f"https://graph.threads.net/v1.0/{threads_id}/threads", data=payload, timeout=(10, 120))
                if item_res.ok:
                    children_ids.append(item_res.json().get("id"))
                else:
                    # Log individual item failure but keep going if possible
                    print(f"Warning: Carousel item failed: {item_res.text}")
            
            if len(children_ids) < 2:
                raise Exception(f"Carousel failed: Need at least 2 successful items, but only got {len(children_ids)}.")

            # Create the parent carousel container
            car_payload = {
                "media_type": "CAROUSEL", 
                "children": ",".join(children_ids), 
                "text": full_text, 
                "access_token": threads_token
            }
            car_res = requests.post(f"https://graph.threads.net/v1.0/{threads_id}/threads", data=car_payload, timeout=(10, 120))
            if not car_res.ok: raise Exception(f"Threads Carousel Parent Error: {car_res.text}")
            creation_id = car_res.json().get("id")

        # --- STEP 2: PUBLISH THE CONTAINER ---
        if not creation_id:
            raise Exception("Critical Error: Container ID was not generated.")

        pub_res = requests.post(
            f"https://graph.threads.net/v1.0/{threads_id}/threads_publish", 
            data={"creation_id": creation_id, "access_token": threads_token},
            timeout=(10, 180) 
        )
        if not pub_res.ok: raise Exception(f"Failed to publish to Threads: {pub_res.text}")
        
    finally:
        if conn: cursor.close(); conn.close()

async def process_pinterest(post_id: int, board_id: str):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s;", (post_id,))
        media_records = cursor.fetchall()

        image_url = next((m['media_url'] for m in media_records if not is_video(m['media_url'])), None)

        if not image_url:
            raise SkipPublishException("Smart Skip: Pinterest requires an image. None were found.")

        if not board_id:
            raise Exception("A valid Pinterest Board ID must be provided.")

        title = post['enhanced_title'][:100] 
        tags_str = " ".join([f"#{tag}" for tag in post['hashtags']]) if post['hashtags'] else ""
        description = f"{post['enhanced_description']}\n\n{tags_str}"[:500] 

        access_token = get_smart_pinterest_token()
        # Removed the os.environ.get board_id line here!

        url = "https://api.pinterest.com/v5/pins"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "title": title,
            "description": description,
            "board_id": board_id, 
            "media_source": {
                "source_type": "image_url",
                "url": image_url
            }
        }

        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code != 201:
            raise Exception(f"Pinterest API Error: {response.text}")

    finally:
        if conn: cursor.close(); conn.close()

async def process_reddit(post_id: int, subreddit_name: str):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s;", (post_id,))
        media_records = cursor.fetchall()

        if not subreddit_name:
            raise Exception("A target Subreddit must be provided (e.g., 'test').")

        # 1. Authenticate with Reddit
        reddit = praw.Reddit(
            client_id=os.environ.get("REDDIT_CLIENT_ID"),
            client_secret=os.environ.get("REDDIT_CLIENT_SECRET"),
            username=os.environ.get("REDDIT_USERNAME"),
            password=os.environ.get("REDDIT_PASSWORD"),
            user_agent="web:social-auto-engine:v1.0 (by u/shoutotb)"
        )

        subreddit = reddit.subreddit(subreddit_name)
        
        # Reddit titles are capped at 300 characters
        title = post['enhanced_title'][:300] 
        tags_str = " ".join([f"#{tag}" for tag in post['hashtags']]) if post['hashtags'] else ""
        full_text = f"{post['enhanced_description']}\n\n{tags_str}"

        # 2. Find the first image (Skip videos for now, as Reddit API video handling is complex)
        image_url = next((m['media_url'] for m in media_records if not is_video(m['media_url'])), None)

        if image_url:
            # Download image to temp file for Reddit upload
            res = requests.get(image_url, stream=True)
            if res.status_code == 200:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_img:
                    temp_img.write(res.content)
                    temp_img_path = temp_img.name

                try:
                    # Submit Image Post
                    subreddit.submit_image(title=title, image_path=temp_img_path)
                finally:
                    if os.path.exists(temp_img_path): os.remove(temp_img_path)
            else:
                raise Exception("Failed to download image from Cloudinary for Reddit.")
        else:
            # Submit Text-Only Post
            subreddit.submit(title=title, selftext=full_text)

    finally:
        if conn: cursor.close(); conn.close()

async def process_mastodon(post_id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        
        # Mastodon allows up to 4 media attachments
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s LIMIT 4;", (post_id,))
        media_records = cursor.fetchall()

        # 1. Initialize the Client
        mastodon = Mastodon(
            access_token=os.environ.get("MASTODON_ACCESS_TOKEN"),
            api_base_url=os.environ.get("MASTODON_API_BASE_URL")
        )

        # 2. Format Text (Mastodon standard limit is 500 characters)
        title = post['enhanced_title']
        tags_str = " ".join([f"#{t}" for t in post['hashtags']]) if post['hashtags'] else ""
        full_text = f"{title}\n\n{post['enhanced_description']}\n\n{tags_str}"
        
        # Safe slice just in case your instance strictly enforces 500
        if len(full_text) > 500:
            full_text = post.get('short_text') or full_text[:490]

        # 3. Handle Media Uploads
        media_ids = []
        if media_records:
            for record in media_records:
                res = requests.get(record['media_url'])
                if res.status_code == 200:
                    # Determine mime type quickly
                    mime_type = "video/mp4" if is_video(record['media_url']) else "image/jpeg"
                    
                    try:
                        # Upload directly from bytes
                        media_dict = mastodon.media_post(res.content, mime_type=mime_type)
                        media_ids.append(media_dict['id'])
                    except Exception as e:
                        print(f"Warning: Mastodon media upload failed: {e}")

        # 4. Post the Status
        mastodon.status_post(status=full_text, media_ids=media_ids if media_ids else None)

    finally:
        if conn: cursor.close(); conn.close()

async def process_bluesky(post_id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s LIMIT 4;", (post_id,))
        media_records = cursor.fetchall()

        # 1. Login
        client = BskyClient()
        client.login(os.environ.get("BLUESKY_HANDLE"), os.environ.get("BLUESKY_APP_PASSWORD"))

        # 2. Smart AI Text Handling
        title = post['enhanced_title']
        desc = post['enhanced_description']
        hashtags = post['hashtags']
        
        # Initial draft
        tags_str = " ".join([f"#{t}" for t in hashtags]) if hashtags else ""
        full_text = f"{title}\n\n{desc}\n\n{tags_str}"

        # If too long, use the AI short version. If it doesn't exist, hard-slice it.
        if len(full_text) > 300:
            print("Post too long for Bluesky. Triggering AI Condenser...")
            full_text = post.get('short_text') or full_text[:290]

        # 3. Handle Media & Post
        if media_records:
            img_url = media_records[0]['media_url']
            img_res = requests.get(img_url)
            if img_res.status_code == 200:
                client.send_image(
                    text=full_text,
                    image=img_res.content,
                    image_alt=title
                )
            else:
                raise Exception("Failed to download image for Bluesky")
        else:
            client.send_post(text=full_text)

    finally:
        if conn: cursor.close(); conn.close()

async def process_discord(post_id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        
        # Discord allows up to 10 embeds per message
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s LIMIT 4;", (post_id,))
        media_records = cursor.fetchall()

        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            raise Exception("Discord Webhook URL is missing from .env")

        # Format Text - Discord uses Markdown, so we can bold the title!
        tags_str = " ".join([f"#{t}" for t in post['hashtags']]) if post['hashtags'] else ""
        full_text = f"@everyone\n\n**{post['enhanced_title']}**\n\n{post['enhanced_description']}\n\n{tags_str}"

        payload = {
            "content": full_text,
            "username": "Shout OTB Publisher" 
        }

        # Handle Media beautifully using Discord's Native Embeds
        if media_records:
            embeds = []
            for record in media_records:
                if is_video(record['media_url']):
                    # Discord embeds don't support video files directly via API, 
                    # so we append the video URL to the text, and Discord will auto-preview it.
                    payload["content"] += f"\n{record['media_url']}"
                else:
                    # Images get beautifully embedded
                    embeds.append({"image": {"url": record['media_url']}})
            
            if embeds:
                payload["embeds"] = embeds

        res = requests.post(webhook_url, json=payload)
        
        if res.status_code not in [200, 204]:
            raise Exception(f"Discord API Error: {res.text}")

    finally:
        if conn: cursor.close(); conn.close()

async def process_telegram(post_id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        
        # Telegram allows up to 10 media items in a carousel
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s LIMIT 10;", (post_id,))
        media_records = cursor.fetchall()

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        
        if not bot_token or not chat_id:
            raise Exception("Telegram credentials missing from .env")

        base_url = f"https://api.telegram.org/bot{bot_token}"
        
        # Format the text
        tags_str = " ".join([f"#{t}" for t in post['hashtags']]) if post['hashtags'] else ""
        full_text = f"🚨 {post['enhanced_title']}\n\n{post['enhanced_description']}\n\n{tags_str}"

        # 1. TEXT ONLY POST
        if not media_records:
            res = requests.post(f"{base_url}/sendMessage", json={
                "chat_id": chat_id,
                "text": full_text
            })
            if not res.ok: raise Exception(f"Telegram API Error: {res.text}")

        # 2. SINGLE IMAGE OR VIDEO
        elif len(media_records) == 1:
            media_url = media_records[0]['media_url']
            is_vid = is_video(media_url)
            
            endpoint = "/sendVideo" if is_vid else "/sendPhoto"
            payload = {
                "chat_id": chat_id,
                "video" if is_vid else "photo": media_url,
                "caption": full_text[:1024] # Telegram limits media captions to 1024 chars
            }
            
            res = requests.post(f"{base_url}{endpoint}", json=payload)
            if not res.ok: raise Exception(f"Telegram Media Error: {res.text}")

        # 3. MULTIPLE MEDIA (CAROUSEL / ALBUM)
        else:
            media_group = []
            for i, record in enumerate(media_records):
                is_vid = is_video(record['media_url'])
                item = {
                    "type": "video" if is_vid else "photo",
                    "media": record['media_url']
                }
                # Attach the caption ONLY to the very first image so it doesn't repeat
                if i == 0:
                    item["caption"] = full_text[:1024]
                media_group.append(item)

            res = requests.post(f"{base_url}/sendMediaGroup", json={
                "chat_id": chat_id,
                "media": media_group
            })
            if not res.ok: raise Exception(f"Telegram Carousel Error: {res.text}")

    finally:
        if conn: cursor.close(); conn.close()

async def process_youtube(post_id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s;", (post_id,))
        media_records = cursor.fetchall()
        
        # SMART LOGIC: Find the first video in the payload
        video_url = next((m['media_url'] for m in media_records if is_video(m['media_url'])), None)
        
        if not video_url:
            raise SkipPublishException("Smart Skip: YouTube requires a video file. Only images were found.")
            
        # Format Text (YouTube Titles have a strict 100 char limit)
        title = post['enhanced_title'][:100] 
        tags_str = " ".join([f"#{tag}" for tag in post['hashtags']]) if post['hashtags'] else ""
        
        # SMART LOGIC: YouTube automatically categorizes videos as Shorts if they are vertical 
        # and under 60 seconds. Appending #Shorts guarantees it gets indexed properly.
        full_desc = f"{post['enhanced_description']}\n\n{tags_str}\n#Shorts #YouTube"

        # 1. Authenticate using the Refresh Token
        creds = Credentials(
            token=None,
            refresh_token=os.environ.get("YOUTUBE_REFRESH_TOKEN"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ.get("YOUTUBE_CLIENT_ID"),
            client_secret=os.environ.get("YOUTUBE_CLIENT_SECRET")
        )
        youtube = build('youtube', 'v3', credentials=creds)

        # 2. Download the video to a temporary file
        res = requests.get(video_url, stream=True)
        if res.status_code != 200:
            raise Exception("Failed to download video from Cloudinary for YouTube.")
            
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video:
            for chunk in res.iter_content(chunk_size=1024*1024):
                if chunk: temp_video.write(chunk)
            temp_video_path = temp_video.name

        # 3. Upload to YouTube
        try:
            body = {
                "snippet": {
                    "title": title,
                    "description": full_desc,
                    "tags": post['hashtags'][:15], 
                    "categoryId": "22" 
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False
                }
            }

            with open(temp_video_path, "rb") as video_file:
                media = MediaIoBaseUpload(video_file, mimetype="video/mp4", chunksize=-1, resumable=True)
                
                request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
                response = request.execute()
                
            if not response.get("id"):
                raise Exception("YouTube API returned success, but no Video ID was found.")
                
        finally:
            # Bulletproof cleanup: Verify it exists, then delete safely
            if os.path.exists(temp_video_path):
                try:
                    os.remove(temp_video_path)
                except Exception as e:
                    print(f"Warning: Could not delete temp file {temp_video_path}: {e}")
            
    finally:
        if conn: 
            cursor.close()
            conn.close()

        
# ==========================================
# 4. API ENDPOINTS
# ==========================================

@router.post("/unified/{post_id}")
async def publish_unified(post_id: int, request: UnifiedPublishRequest):
    if request.admin_password != os.environ.get("ADMIN_PUBLISH_PASSWORD"):
        raise HTTPException(status_code=401, detail="Incorrect Admin Password")
        
    if not request.platforms:
        raise HTTPException(status_code=400, detail="No platforms selected")

    results = []
    
    for platform in request.platforms:
        try:
            # Check for the platform and execute the corresponding processor
            if platform == "LinkedIn":
                await process_linkedin(post_id) 
            elif platform == "Facebook":
                await process_facebook(post_id)
            elif platform == "Instagram":
                await process_instagram(post_id)
            elif platform in ["X", "Twitter/X"]: 
                await process_x(post_id)
            elif platform == "YouTube":
                await process_youtube(post_id)
            elif platform == "Bluesky":           
                await process_bluesky(post_id)     
            elif platform == "Discord":            
                await process_discord(post_id)     
            elif platform == "Telegram":           
                await process_telegram(post_id)    
            elif platform == "Mastodon":           
                await process_mastodon(post_id)   
            elif platform == "Threads":
                await process_threads(post_id)
            elif platform == "Pinterest":
                await process_pinterest(post_id, request.pinterest_board_id)
            elif platform == "Reddit":                 
                await process_reddit(post_id, request.reddit_subreddit)
            else:
                raise Exception(f"Unknown platform identifier: {platform}")

            log_publish_attempt(post_id, platform, "Success")
            results.append({"platform": platform, "status": "Success"})
            
        except SkipPublishException as skip_e:
            skip_msg = str(skip_e)
            log_publish_attempt(post_id, platform, "Skipped", skip_msg)
            results.append({"platform": platform, "status": "Skipped", "error": skip_msg})
                
        except Exception as e:
            error_str = str(e)
            log_publish_attempt(post_id, platform, "Failed", error_str)
            results.append({"platform": platform, "status": "Failed", "error": error_str})

    if any(r["status"] in ["Success", "Skipped"] for r in results):
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE posts SET status = 'Published' WHERE id = %s;", (post_id,))
            conn.commit()
            cursor.close()
            conn.close()

    return {"message": "Publishing cycle complete", "logs": results}

@router.get("/logs/{post_id}")
async def get_publish_logs(post_id: int):
    """Fetches the success/error history for a specific post."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM publish_logs WHERE post_id = %s ORDER BY published_at DESC;", (post_id,))
        logs = cursor.fetchall()
        
        # Format timestamps for JSON response
        for log in logs:
            if log.get('published_at'):
                log['published_at'] = log['published_at'].isoformat()
        return {"logs": logs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()