import os
import tempfile
import praw
import requests
import json
import asyncio
import base64
from atproto import Client as BskyClient
from typing import List, Optional
from pydantic import BaseModel
import time
from datetime import datetime
from pydantic import BaseModel
import tweepy
import asyncio
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.core.db import get_db_connection
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from mastodon import Mastodon

load_dotenv()

router = APIRouter()

MAX_CONCURRENT_PLATFORMS = 3
limiter = asyncio.Semaphore(MAX_CONCURRENT_PLATFORMS)
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
    google_cta_type: Optional[str] = "LEARN_MORE"  
    google_cta_url: Optional[str] = "https://shoutotb.com"

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

def download_media_locally(media_records):
    local_paths = []
    for record in media_records:
        url = record['media_url']
        suffix = ".mp4" if is_video(url) else ".jpg"
        # Download in chunks (streaming) to keep RAM usage near zero
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            fd, path = tempfile.mkstemp(suffix=suffix)
            with os.fdopen(fd, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            local_paths.append({"path": path, "url": url, "is_video": is_video(url)})
    return local_paths
   
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

def upload_media_to_linkedin(local_path, access_token, author_urn, is_vid): # 🔥 Changed media_url to local_path
    headers = {"Authorization": f"Bearer {access_token}", "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"}
    recipe = "urn:li:digitalmediaRecipe:feedshare-video" if is_vid else "urn:li:digitalmediaRecipe:feedshare-image"
    
    # 1. Register Upload
    reg_payload = {"registerUploadRequest": {"recipes": [recipe], "owner": author_urn, "serviceRelationships": [{"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}]}}
    reg_response = requests.post("https://api.linkedin.com/v2/assets?action=registerUpload", headers=headers, json=reg_payload)
    
    upload_url = reg_response.json()['value']['uploadMechanism']['com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest']['uploadUrl']
    asset_urn = reg_response.json()['value']['asset']

    # 2. 🔥 REPLACEMENT: Open local file instead of downloading
    with open(local_path, 'rb') as f:
        upload_headers = {"Authorization": f"Bearer {access_token}"}
        if is_vid: upload_headers["Content-Type"] = "application/octet-stream"
        requests.put(upload_url, headers=upload_headers, data=f)
        
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

async def process_x(post_id: int, local_media: list): # 🔥 Added local_media
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        
        media_ids = []
        # 🔥 REPLACEMENT: Use the paths from local_media instead of downloading
        for m in local_media:
            if not m['is_video']: # X handles images and videos differently in V1.1
                media_upload = api_v1.media_upload(m['path'])
                media_ids.append(media_upload.media_id)

        tweet_text = post.get('short_text') or format_tweet_text(post['enhanced_title'], post['enhanced_description'], post['hashtags'])
        client.create_tweet(text=tweet_text, media_ids=media_ids if media_ids else None)

    except Exception as e:
        raise Exception(str(e))
    finally:
        if conn: cursor.close(); conn.close()

async def process_linkedin(post_id: int, local_media: list):
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
        
        if local_media:
            for m in local_media:
                # 🔥 REPLACEMENT: Pass the path
                asset_urn = upload_media_to_linkedin(m['path'], access_token, author_urn, m['is_video'])

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
        
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s LIMIT 10;", (post_id,))
        media_records = cursor.fetchall()

        if not media_records:
            raise SkipPublishException("Smart Skip: Instagram requires an image or video. No media found.")
            
        full_text = f"{post['enhanced_title']}\n\n{post['enhanced_description']}\n\n" + (" ".join([f"#{t}" for t in post['hashtags']]) if post['hashtags'] else "")
        page_token = get_page_access_token(os.environ.get("META_ACCESS_TOKEN"), os.environ.get("FACEBOOK_PAGE_ID"))
        ig_id = os.environ.get("INSTAGRAM_ACCOUNT_ID")
        
        # --- STEP 1: Create the Media Container ---
        if len(media_records) == 1:
            safe_url = optimize_media_url_for_ig(media_records[0]['media_url'])
            is_vid = is_video(media_records[0]['media_url'])
            
            container_payload = {"caption": full_text, "access_token": page_token}
            if is_vid:
                container_payload["video_url"] = safe_url
                container_payload["media_type"] = "REELS"
            else:
                container_payload["image_url"] = safe_url
                
            cont_response = requests.post(f"https://graph.facebook.com/v19.0/{ig_id}/media", data=container_payload, timeout=(10, 180))
            if cont_response.status_code != 200: raise Exception(f"IG container failed: {cont_response.text}")
            creation_id = cont_response.json().get("id")
            
        else:
            # Multi-media Carousels 
            children_ids = []
            for record in media_records:
                safe_url = optimize_media_url_for_ig(record['media_url'])
                is_vid = is_video(record['media_url'])
                payload = {"is_carousel_item": "true", "access_token": page_token, "video_url" if is_vid else "image_url": safe_url}
                if is_vid: payload["media_type"] = "VIDEO"
                
                item_res = requests.post(f"https://graph.facebook.com/v19.0/{ig_id}/media", data=payload, timeout=(10, 120))
                if item_res.status_code == 200: children_ids.append(item_res.json().get("id"))
            
            car_res = requests.post(f"https://graph.facebook.com/v19.0/{ig_id}/media", data={"media_type": "CAROUSEL", "children": ",".join(children_ids), "caption": full_text, "access_token": page_token}, timeout=(10, 120))
            if car_res.status_code != 200: raise Exception(f"IG Carousel Parent failed: {car_res.text}")
            creation_id = car_res.json().get("id")

        # --- STEP 2: Wait for Meta to finish processing the media before publishing 
        is_ready = False
        for _ in range(15): # Wait up to 75 seconds for Meta to process
            time.sleep(5)
            status_res = requests.get(f"https://graph.facebook.com/v19.0/{creation_id}?fields=status_code&access_token={page_token}")
            if status_res.status_code == 200:
                status = status_res.json().get('status_code')
                if status == 'FINISHED':
                    is_ready = True
                    break
                elif status == 'ERROR':
                    raise Exception("Instagram failed to process the media file (Internal Meta Error).")
        
        if not is_ready:
            raise Exception("Instagram media processing timed out after 75 seconds.")

        # --- STEP 3: Publish ---
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
                    child_id = item_res.json().get("id")
                    
                    # 🔥 THE FIX: Wait for Meta to finish processing this specific child
                    is_ready = False
                    for _ in range(12): # Wait up to 60 seconds per item
                        time.sleep(5)
                        status_res = requests.get(f"https://graph.threads.net/v1.0/{child_id}?fields=status&access_token={threads_token}")
                        if status_res.status_code == 200:
                            status = status_res.json().get('status')
                            if status == 'FINISHED':
                                is_ready = True
                                break
                            elif status == 'ERROR':
                                print(f"Warning: Meta failed to process child {child_id}")
                                break
                                
                    if is_ready:
                        children_ids.append(child_id)
                    else:
                        print(f"Warning: Child {child_id} timed out during processing.")
                else:
                    print(f"Warning: Carousel item failed: {item_res.text}")
            
            # Verify we have enough successfully processed children
            if len(children_ids) < 2:
                raise Exception(f"Carousel failed: Need at least 2 fully processed items, but only got {len(children_ids)}.")

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

async def process_reddit(post_id: int, subreddit_name: str, local_media: list):
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
        first_image = next((m for m in local_media if not m['is_video']), None)

        if first_image:
            # We don't need 'requests.get' or 'tempfile' anymore!
            subreddit.submit_image(title=title, image_path=first_image['path'])
        else:
            subreddit.submit(title=title, selftext=full_text)

    finally:
        if conn: cursor.close(); conn.close()

async def process_mastodon(post_id: int, local_media: list): # 🔥 Added local_media
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()

        mastodon = Mastodon(
            access_token=os.environ.get("MASTODON_ACCESS_TOKEN"),
            api_base_url=os.environ.get("MASTODON_API_BASE_URL")
        )

        # Uploading from local disk
        media_ids = []
        for m in local_media:
            mime_type = "video/mp4" if m['is_video'] else "image/jpeg"
            # We open the path directly - this uses almost ZERO RAM
            with open(m['path'], 'rb') as f:
                media_dict = mastodon.media_post(f, mime_type=mime_type)
                media_ids.append(media_dict['id'])

        tags_str = " ".join([f"#{t}" for t in post['hashtags']]) if post['hashtags'] else ""
        full_text = f"{post['enhanced_title']}\n\n{post['enhanced_description']}\n\n{tags_str}"
        if len(full_text) > 500:
            full_text = post.get('short_text') or full_text[:490]

        mastodon.status_post(status=full_text, media_ids=media_ids if media_ids else None)
    finally:
        if conn: cursor.close(); conn.close()

async def process_bluesky(post_id: int, local_media: list):
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
        first_image = next((m for m in local_media if not m['is_video']), None)

        if first_image:
            with open(first_image['path'], 'rb') as f:
                client.send_image(
                    text=full_text,
                    image=f.read(),
                    image_alt=post['enhanced_title']
                )
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

async def process_telegram(post_id: int, local_media: list):
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
        if len(local_media) == 1:
            m = local_media[0]
            endpoint = "/sendVideo" if m['is_video'] else "/sendPhoto"
            with open(m['path'], 'rb') as f:
                res = requests.post(f"{base_url}{endpoint}", 
                    data={"chat_id": chat_id, "caption": full_text[:1024]},
                    files={("video" if m['is_video'] else "photo"): f} # 🔥 Send as file
                )

        # 3. MULTIPLE MEDIA (ALBUM)
        else:
            files_to_send = {}
            media_group = []
            for i, m in enumerate(local_media):
                file_key = f"file_{i}"
                # Open the file and keep the pointer in the files_to_send dict
                files_to_send[file_key] = open(m['path'], 'rb')
                
                media_group.append({
                    "type": "video" if m['is_video'] else "photo",
                    "media": f"attach://{file_key}", # 🔥 Reference the attached file
                    "caption": full_text[:1024] if i == 0 else ""
                })

            requests.post(f"{base_url}/sendMediaGroup", 
                data={"chat_id": chat_id, "media": json.dumps(media_group)},
                files=files_to_send
            )
            # Close all file pointers
            for f in files_to_send.values(): f.close()

    finally:
        if conn: cursor.close(); conn.close()

async def process_google(post_id: int, cta_type: str, cta_url: str):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        
        # Google only supports 1 image per post
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s LIMIT 1;", (post_id,))
        media_record = cursor.fetchone()

        location_name = os.environ.get("GOOGLE_LOCATION_NAME") 
        refresh_token = os.environ.get("GOOGLE_BUSINESS_REFRESH_TOKEN")
        
        if not location_name or not refresh_token or refresh_token == "pending_approval":
            raise Exception("Google Business credentials missing or pending approval.")

        # 1. Refresh the Access Token
        token_res = requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": os.environ.get("GOOGLE_CLIENT_ID"),
            "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET"),
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        })
        if not token_res.ok: raise Exception(f"Failed to refresh Google token: {token_res.text}")
        access_token = token_res.json().get("access_token")

        # 2. Build the Payload
        # Google limits posts to 1500 chars
        full_text = f"{post['enhanced_title']}\n\n{post['enhanced_description']}"[:1500]

        payload = {
            "languageCode": "en-US",
            "summary": full_text
        }

        # Add Call To Action Button
        if cta_type and cta_type != "NONE":
            payload["callToAction"] = {
                "actionType": cta_type,
                "url": cta_url if cta_url else "https://shoutotb.com" # Fallback URL
            }

        # Add Image (Google fetches directly from your Cloudinary URL)
        if media_record and not is_video(media_record['media_url']):
            payload["media"] = [{"mediaFormat": "PHOTO", "sourceUrl": media_record['media_url']}]

        # 3. Publish to Google
        headers = {"Authorization": f"Bearer {access_token}"}
        endpoint = f"https://mybusiness.googleapis.com/v4/{location_name}/localPosts"
        
        publish_res = requests.post(endpoint, headers=headers, json=payload)
        
        if not publish_res.ok:
            raise Exception(f"Google Business API Error: {publish_res.text}")

    finally:
        if conn: cursor.close(); conn.close()

async def process_youtube(post_id: int, local_media: list):
    """
    Processes YouTube uploads using pre-downloaded local media to save RAM 
    and prevent timeouts on Render.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        
        # Find the video in our pre-downloaded local_media list
        video_item = next((m for m in local_media if m['is_video']), None)
        
        if not video_item:
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

        # 2. Upload to YouTube using the local file path
        body = {
            "snippet": {
                "title": title,
                "description": full_desc,
                "tags": post['hashtags'][:15], 
                "categoryId": "22" # People & Blogs
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False
            }
        }

        # 🔥 REPLACEMENT: Open the local path directly. 
        # This streams the file from disk to YouTube without loading it into RAM.
        with open(video_item['path'], "rb") as video_file:
            media = MediaIoBaseUpload(video_file, mimetype="video/mp4", chunksize=-1, resumable=True)
            
            request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
            response = request.execute()
            
        if not response.get("id"):
            raise Exception("YouTube API returned success, but no Video ID was found.")
                
    finally:
        # Note: We no longer delete the file here because 'start_publishing_cycle' 
        # handles the final cleanup after ALL platforms are finished.
        if conn: 
            cursor.close()
            conn.close()
        
# ==========================================
# 4. API ENDPOINTS
# ==========================================

@router.post("/unified/{post_id}")
async def publish_unified(post_id: int, request: UnifiedPublishRequest, background_tasks: BackgroundTasks):
    if request.admin_password != os.environ.get("ADMIN_PUBLISH_PASSWORD"):
        raise HTTPException(status_code=401, detail="Incorrect Admin Password")
        
    if not request.platforms:
        raise HTTPException(status_code=400, detail="No platforms selected")

    # This inner function now uses the limiter to ensure we don't exceed API rate limits, and it also accepts the pre-downloaded media list
    async def run_processor_with_limit(platform: str, post_id: int, local_media: list, request: UnifiedPublishRequest):
        async with limiter: 
            try:
                # 🔥 Pass 'local_media' to the platforms that support local file uploads
                if platform == "LinkedIn": await process_linkedin(post_id, local_media) 
                elif platform == "Facebook": await process_facebook(post_id) # Meta requires URLs
                elif platform == "Instagram": await process_instagram(post_id) # Meta requires URLs
                elif platform in ["X", "Twitter/X"]: await process_x(post_id, local_media)
                elif platform == "YouTube": await process_youtube(post_id, local_media)
                elif platform == "Bluesky": await process_bluesky(post_id, local_media)     
                elif platform == "Threads": await process_threads(post_id) # Meta requires URLs
                elif platform == "Pinterest": await process_pinterest(post_id, request.pinterest_board_id)
                elif platform == "Reddit": await process_reddit(post_id, local_media)
                elif platform == "Discord": await process_discord(post_id) # Webhooks prefer URLs
                elif platform == "Telegram": await process_telegram(post_id, local_media)    
                elif platform == "Mastodon": await process_mastodon(post_id, local_media) 
                elif platform == "Google Business": await process_google(post_id, request.google_cta_type, request.google_cta_url)
                
                log_publish_attempt(post_id, platform, "Success")
            except SkipPublishException as skip_e:
                log_publish_attempt(post_id, platform, "Skipped", str(skip_e))
            except Exception as e:
                log_publish_attempt(post_id, platform, "Failed", str(e))

    # --- 2. DEFINE THE BACKGROUND JOB ---
    async def start_publishing_cycle(post_id, request):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s;", (post_id,))
        media_records = cursor.fetchall()
        cursor.close()
        conn.close()

        # 🔥 DOWNLOAD ONCE: Get all images onto disk first
        local_media = download_media_locally(media_records)

        try:
            # Pass 'local_media' to your tasks instead of making them download it
            tasks = [run_processor_with_limit(plat, post_id, local_media, request) for plat in request.platforms]
            await asyncio.gather(*tasks)
        finally:
            # 🔥 CLEANUP: Delete the temp files after all platforms are done
            for m in local_media:
                if os.path.exists(m['path']):
                    os.remove(m['path'])

    # --- 3. FIRE AND FORGET ---
    # We tell FastAPI to run this in the background
    background_tasks.add_task(start_publishing_cycle, post_id, request)

    # Return INSTANTLY to the frontend to avoid Cloudflare/Render timeouts
    return {"message": "Publishing started in background. Check 'View Logs' in a moment for results."}

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