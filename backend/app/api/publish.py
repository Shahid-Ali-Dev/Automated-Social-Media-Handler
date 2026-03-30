import os
import tempfile
import requests
import time
import tweepy
from fastapi import APIRouter, HTTPException
from app.core.db import get_db_connection
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# 1. Authenticate with X (Twitter)
# X requires v1.1 API to upload media, and v2 API to post the actual tweet. Tweepy handles both.
auth = tweepy.OAuth1UserHandler(
    os.environ.get("X_API_KEY"),
    os.environ.get("X_API_SECRET"),
    os.environ.get("X_ACCESS_TOKEN"),
    os.environ.get("X_ACCESS_TOKEN_SECRET")
)
api_v1 = tweepy.API(auth) # For media uploads

client = tweepy.Client(
    consumer_key=os.environ.get("X_API_KEY"),
    consumer_secret=os.environ.get("X_API_SECRET"),
    access_token=os.environ.get("X_ACCESS_TOKEN"),
    access_token_secret=os.environ.get("X_ACCESS_TOKEN_SECRET")
) # For text and publishing

def is_video(url: str) -> bool:
    """Checks if the Cloudinary URL is a video file."""
    video_extensions = ['.mp4', '.mov', '.webm', '.avi', '.mkv']
    return any(ext in url.lower() for ext in video_extensions) or "/video/upload/" in url

def format_tweet_text(title, description, hashtags):
    """Formats the post and ensures it stays under X's 280-character limit."""
    tags_str = " ".join([f"#{tag}" for tag in hashtags]) if hashtags else ""
    
    # Construct the ideal tweet
    tweet = f"{title}\n\n{description}\n\n{tags_str}"
    
    # If it's too long, truncate the description
    if len(tweet) > 280:
        available_space = 280 - len(title) - len(tags_str) - 10 # 10 chars for spacing/ellipsis
        truncated_desc = description[:available_space] + "..."
        tweet = f"{title}\n\n{truncated_desc}\n\n{tags_str}"
        
    return tweet

@router.post("/x/{post_id}")
async def publish_to_x(post_id: int):
    """Fetches a post and its media, then publishes it to X."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    try:
        cursor = conn.cursor()
        
        # 1. Fetch Post Data
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
            
        # 2. Fetch Attached Media (Limit 4 for X)
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s LIMIT 4;", (post_id,))
        media_records = cursor.fetchall()
        
        media_ids = []
        
        # 3. Process and Upload Media to X
        if media_records:
            for record in media_records:
                media_url = record['media_url']
                
                # Download image from Cloudinary temporarily
                response = requests.get(media_url)
                if response.status_code == 200:
                    # Create a temporary file to hold the image
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
                        temp_file.write(response.content)
                        temp_file_path = temp_file.name
                        
                    # Upload to X via v1.1 API
                    media_upload = api_v1.media_upload(temp_file_path)
                    media_ids.append(media_upload.media_id)
                    
                    # Clean up the temporary file
                    os.remove(temp_file_path)

        # 4. Format Text and Publish!
        tweet_text = format_tweet_text(post['enhanced_title'], post['enhanced_description'], post['hashtags'])
        
        # If we have media, attach it. Otherwise, post text only.
        if media_ids:
            response = client.create_tweet(text=tweet_text, media_ids=media_ids)
        else:
            response = client.create_tweet(text=tweet_text)
            
        # 5. Update Database Status
        cursor.execute("UPDATE posts SET status = 'Posted' WHERE id = %s;", (post_id,))
        conn.commit()
        
        return {"message": "Successfully posted to X!", "tweet_id": response.data['id']}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to publish: {str(e)}")
    finally:
        cursor.close()
        conn.close()

def get_linkedin_user_urn(access_token):
    """Dynamically fetches the exact URN for the authenticated user using the latest LinkedIn standards."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "LinkedIn-Version": "202401" 
    }
    response = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers)
    
    if response.status_code == 200:
        sub_id = response.json().get("sub")
        if not sub_id.startswith("urn:li:person:"):
            return f"urn:li:person:{sub_id}"
        return sub_id
    else:
        raise Exception(f"Failed to fetch URN. Error: {response.text}")

def upload_media_to_linkedin(media_url, access_token, author_urn, is_vid):
    """Dynamically handles both Images and Videos for LinkedIn."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json"
    }

    # Step 1: Register the upload using the correct recipe
    recipe = "urn:li:digitalmediaRecipe:feedshare-video" if is_vid else "urn:li:digitalmediaRecipe:feedshare-image"
    
    register_url = "https://api.linkedin.com/v2/assets?action=registerUpload"
    register_payload = {
        "registerUploadRequest": {
            "recipes": [recipe],
            "owner": author_urn,
            "serviceRelationships": [
                {"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}
            ]
        }
    }
    
    reg_response = requests.post(register_url, headers=headers, json=register_payload)
    if reg_response.status_code != 200:
        raise Exception(f"Failed to register media: {reg_response.text}")
        
    reg_data = reg_response.json()
    upload_url = reg_data['value']['uploadMechanism']['com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest']['uploadUrl']
    asset_urn = reg_data['value']['asset']

    # Step 2 & 3: Download from Cloudinary and Upload binary to LinkedIn
    media_response = requests.get(media_url)
    upload_headers = {"Authorization": f"Bearer {access_token}"}
    
    # LinkedIn requires application/octet-stream for videos to process correctly
    if is_vid:
        upload_headers["Content-Type"] = "application/octet-stream"
        
    upload_res = requests.put(upload_url, headers=upload_headers, data=media_response.content)
    
    if upload_res.status_code not in [200, 201]:
        raise Exception(f"Failed to upload binary to LinkedIn: {upload_res.text}")

    return asset_urn

@router.post("/linkedin/{post_id}")
async def publish_to_linkedin(post_id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s LIMIT 9;", (post_id,))
        media_records = cursor.fetchall()
            
        title = post['enhanced_title']
        description = post['enhanced_description']
        tags_str = " ".join([f"#{tag}" for tag in post['hashtags']]) if post['hashtags'] else ""
        full_text = f"{title}\n\n{description}\n\n{tags_str}"
        
        access_token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
        author_urn = get_linkedin_user_urn(access_token)
        
        linkedin_media_items = []
        is_post_video = False
        
        if media_records:
            for record in media_records:
                is_vid = is_video(record['media_url'])
                if is_vid: is_post_video = True
                
                # Use our upgraded helper function
                asset_urn = upload_media_to_linkedin(record['media_url'], access_token, author_urn, is_vid)
                
                linkedin_media_items.append({
                    "status": "READY",
                    "description": {"text": title}, 
                    "media": asset_urn,
                    "title": {"text": title}
                })

        # Set category to VIDEO or IMAGE
        if not linkedin_media_items:
            category = "NONE"
        else:
            category = "VIDEO" if is_post_video else "IMAGE"

        share_content = {
            "shareCommentary": {"text": full_text},
            "shareMediaCategory": category
        }
        
        if linkedin_media_items:
            share_content["media"] = linkedin_media_items

        payload = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {"com.linkedin.ugc.ShareContent": share_content},
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
        }
        
        url = "https://api.linkedin.com/v2/ugcPosts"
        headers = {"Authorization": f"Bearer {access_token}", "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"}
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code != 201:
            raise Exception(f"LinkedIn API Error: {response.text}")
            
        cursor.execute("UPDATE posts SET status = 'Posted' WHERE id = %s;", (post_id,))
        conn.commit()
        return {"message": "Successfully posted to LinkedIn!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn: cursor.close(); conn.close()

def get_page_access_token(system_user_token, page_id):
    """Exchanges the System User Token for a dedicated Page Access Token."""
    url = f"https://graph.facebook.com/v19.0/{page_id}?fields=access_token"
    response = requests.get(url, params={"access_token": system_user_token})
    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        raise Exception(f"Failed to swap for Page Access Token: {response.text}")

def optimize_media_url_for_ig(url):
    """
    Tells Cloudinary to instantly pad the image to a 4:5 (portrait) 
    aspect ratio with black bars so Instagram NEVER rejects it.
    """
    if "/upload/" in url:
        return url.replace("/upload/", "/upload/c_pad,ar_4:5,b_black/")
    return url

@router.post("/facebook/{post_id}")
async def publish_to_facebook(post_id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s LIMIT 10;", (post_id,))
        media_records = cursor.fetchall()
        
        full_text = f"{post['enhanced_title']}\n\n{post['enhanced_description']}\n\n" + (" ".join([f"#{t}" for t in post['hashtags']]) if post['hashtags'] else "")
        
        system_token = os.environ.get("META_ACCESS_TOKEN")
        page_id = os.environ.get("FACEBOOK_PAGE_ID")
        page_token = get_page_access_token(system_token, page_id)
        
        if not media_records:
            url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
            response = requests.post(url, data={"message": full_text, "access_token": page_token})
            
        elif len(media_records) == 1:
            is_vid = is_video(media_records[0]['media_url'])
            if is_vid:
                # FB Video Endpoint & Payload
                url = f"https://graph.facebook.com/v19.0/{page_id}/videos"
                payload = {"file_url": media_records[0]['media_url'], "description": full_text, "access_token": page_token}
            else:
                # FB Photo Endpoint
                url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
                payload = {"url": media_records[0]['media_url'], "message": full_text, "access_token": page_token}
            response = requests.post(url, data=payload)
            
        else:
            # Multi-image carousel logic remains the same (FB API handles video carousels poorly, so stick to images for carousels)
            attached_media = []
            for record in media_records:
                photo_url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
                photo_res = requests.post(photo_url, data={"url": record['media_url'], "published": "false", "access_token": page_token})
                if photo_res.status_code == 200: attached_media.append(photo_res.json().get("id"))
            
            payload = {"message": full_text, "access_token": page_token}
            for i, media_id in enumerate(attached_media): payload[f"attached_media[{i}]"] = f'{{"media_fbid":"{media_id}"}}'
            response = requests.post(f"https://graph.facebook.com/v19.0/{page_id}/feed", data=payload)

        if response.status_code != 200:
            raise Exception(f"Facebook API Error: {response.text}")
            
        cursor.execute("UPDATE posts SET status = 'Posted' WHERE id = %s;", (post_id,))
        conn.commit()
        return {"message": "Successfully posted to Facebook!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn: cursor.close(); conn.close()


@router.post("/instagram/{post_id}")
async def publish_to_instagram(post_id: int):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s LIMIT 10;", (post_id,))
        media_records = cursor.fetchall()
        if not media_records: raise HTTPException(status_code=400, detail="Instagram requires media.")
            
        full_text = f"{post['enhanced_title']}\n\n{post['enhanced_description']}\n\n" + (" ".join([f"#{t}" for t in post['hashtags']]) if post['hashtags'] else "")
        page_token = get_page_access_token(os.environ.get("META_ACCESS_TOKEN"), os.environ.get("FACEBOOK_PAGE_ID"))
        ig_id = os.environ.get("INSTAGRAM_ACCOUNT_ID")
        
        if len(media_records) == 1:
            safe_url = optimize_media_url_for_ig(media_records[0]['media_url'])
            is_vid = is_video(media_records[0]['media_url'])
            
            container_payload = {"caption": full_text, "access_token": page_token}
            if is_vid:
                container_payload["video_url"] = safe_url
                container_payload["media_type"] = "VIDEO"
            else:
                container_payload["image_url"] = safe_url
                
            cont_response = requests.post(f"https://graph.facebook.com/v19.0/{ig_id}/media", data=container_payload)
            if cont_response.status_code != 200: raise Exception(f"IG container failed: {cont_response.text}")
            creation_id = cont_response.json().get("id")
            
            # 🔥 IG VIDEO FIX: Wait for Meta's servers to process the video before publishing
            if is_vid:
                status_url = f"https://graph.facebook.com/v19.0/{creation_id}?fields=status_code&access_token={page_token}"
                for _ in range(10):  # Check 10 times, wait 3 seconds each time
                    time.sleep(3)
                    status_res = requests.get(status_url)
                    if status_res.status_code == 200 and status_res.json().get('status_code') == 'FINISHED':
                        break
        else:
            # Carousel Logic remains the same
            children_ids = []
            for record in media_records:
                safe_url = optimize_media_url_for_ig(record['media_url'])
                is_vid = is_video(record['media_url'])
                payload = {"is_carousel_item": "true", "access_token": page_token}
                if is_vid:
                    payload["video_url"] = safe_url
                    payload["media_type"] = "VIDEO"
                else:
                    payload["image_url"] = safe_url
                item_res = requests.post(f"https://graph.facebook.com/v19.0/{ig_id}/media", data=payload)
                if item_res.status_code == 200: children_ids.append(item_res.json().get("id"))
            
            car_res = requests.post(f"https://graph.facebook.com/v19.0/{ig_id}/media", data={"media_type": "CAROUSEL", "children": ",".join(children_ids), "caption": full_text, "access_token": page_token})
            creation_id = car_res.json().get("id")

        # Publish
        pub_response = requests.post(f"https://graph.facebook.com/v19.0/{ig_id}/media_publish", data={"creation_id": creation_id, "access_token": page_token})
        if pub_response.status_code != 200: raise Exception(f"Failed to publish to IG: {pub_response.text}")
            
        cursor.execute("UPDATE posts SET status = 'Posted' WHERE id = %s;", (post_id,))
        conn.commit()
        return {"message": "Successfully posted to Instagram!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn: cursor.close(); conn.close()