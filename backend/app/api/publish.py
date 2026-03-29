import os
import tempfile
import requests
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

def upload_image_to_linkedin(image_url, access_token, author_urn):
    """The 3-step dance to get an image from Cloudinary into LinkedIn's servers."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json"
    }

    # Step 1: Register the upload
    register_url = "https://api.linkedin.com/v2/assets?action=registerUpload"
    register_payload = {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "owner": author_urn,
            "serviceRelationships": [
                {"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}
            ]
        }
    }
    
    reg_response = requests.post(register_url, headers=headers, json=register_payload)
    if reg_response.status_code != 200:
        raise Exception(f"Failed to register image: {reg_response.text}")
        
    reg_data = reg_response.json()
    upload_url = reg_data['value']['uploadMechanism']['com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest']['uploadUrl']
    asset_urn = reg_data['value']['asset']

    # Step 2: Download from Cloudinary
    img_response = requests.get(image_url)
    if img_response.status_code != 200:
        raise Exception("Failed to download image from Cloudinary")

    # Step 3: Upload the binary data to LinkedIn
    upload_headers = {"Authorization": f"Bearer {access_token}"}
    upload_res = requests.put(upload_url, headers=upload_headers, data=img_response.content)
    
    if upload_res.status_code != 201:
        raise Exception(f"Failed to upload binary to LinkedIn: {upload_res.text}")

    return asset_urn

@router.post("/linkedin/{post_id}")
async def publish_to_linkedin(post_id: int):
    """Fetches a post and publishes it to LinkedIn, handling multiple images."""
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
            
        # 2. Fetch Attached Media (LinkedIn allows up to 9 images in a multi-image post)
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s LIMIT 9;", (post_id,))
        media_records = cursor.fetchall()
            
        # 3. Format the Text Content
        title = post['enhanced_title']
        description = post['enhanced_description']
        hashtags = post['hashtags']
        tags_str = " ".join([f"#{tag}" for tag in hashtags]) if hashtags else ""
        full_text = f"{title}\n\n{description}\n\n{tags_str}"
        
        # 4. Prepare LinkedIn Credentials
        access_token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
        author_urn = get_linkedin_user_urn(access_token)
        
        # 5. Process Images if they exist
        linkedin_media_items = []
        if media_records:
            for record in media_records:
                # Upload each image and get the LinkedIn Asset URN back
                asset_urn = upload_image_to_linkedin(record['media_url'], access_token, author_urn)
                
                # Format it for the final post payload
                linkedin_media_items.append({
                    "status": "READY",
                    "description": {"text": title}, # Alt text
                    "media": asset_urn,
                    "title": {"text": title}
                })

        # 6. Construct the Final Payload
        share_content = {
            "shareCommentary": {"text": full_text},
            "shareMediaCategory": "IMAGE" if linkedin_media_items else "NONE"
        }
        
        # Only attach the media array if we actually have images
        if linkedin_media_items:
            share_content["media"] = linkedin_media_items

        payload = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": share_content
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }
        
        # 7. Send the Final Post to LinkedIn!
        url = "https://api.linkedin.com/v2/ugcPosts"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code != 201:
            raise Exception(f"LinkedIn API Error: {response.text}")
            
        # 8. Update Database Status
        cursor.execute("UPDATE posts SET status = 'Posted' WHERE id = %s;", (post_id,))
        conn.commit()
        
        return {"message": "Successfully posted to LinkedIn with media!"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to publish: {str(e)}")
    finally:
        cursor.close()
        conn.close()

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
    """Publishes to Facebook, automatically handling single or multiple images."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")
        
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        
        # Grab up to 10 images (Facebook's carousel limit)
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s LIMIT 10;", (post_id,))
        media_records = cursor.fetchall()
        
        title = post['enhanced_title']
        description = post['enhanced_description']
        hashtags = " ".join([f"#{tag}" for tag in post['hashtags']]) if post['hashtags'] else ""
        full_text = f"{title}\n\n{description}\n\n{hashtags}"
        
        system_token = os.environ.get("META_ACCESS_TOKEN")
        page_id = os.environ.get("FACEBOOK_PAGE_ID")
        page_token = get_page_access_token(system_token, page_id)
        
        if not media_records:
            # TEXT ONLY
            url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
            payload = {"message": full_text, "access_token": page_token}
            response = requests.post(url, data=payload)
            
        elif len(media_records) == 1:
            # SINGLE IMAGE
            url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
            payload = {"url": media_records[0]['media_url'], "message": full_text, "access_token": page_token}
            response = requests.post(url, data=payload)
            
        else:
            # MULTI-IMAGE CAROUSEL
            attached_media = []
            # Step 1: Upload each photo as "unpublished" to get an ID
            for record in media_records:
                photo_url = f"https://graph.facebook.com/v19.0/{page_id}/photos"
                photo_payload = {"url": record['media_url'], "published": "false", "access_token": page_token}
                photo_res = requests.post(photo_url, data=photo_payload)
                if photo_res.status_code == 200:
                    attached_media.append(photo_res.json().get("id"))
            
            # Step 2: Attach all IDs to a single feed post
            feed_url = f"https://graph.facebook.com/v19.0/{page_id}/feed"
            payload = {"message": full_text, "access_token": page_token}
            for i, media_id in enumerate(attached_media):
                payload[f"attached_media[{i}]"] = f'{{"media_fbid":"{media_id}"}}'
                
            response = requests.post(feed_url, data=payload)

        if response.status_code != 200:
            raise Exception(f"Facebook API Error: {response.text}")
            
        cursor.execute("UPDATE posts SET status = 'Posted' WHERE id = %s;", (post_id,))
        conn.commit()
        return {"message": "Successfully posted to Facebook!"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@router.post("/instagram/{post_id}")
async def publish_to_instagram(post_id: int):
    """Publishes to Instagram, automatically handling aspect ratios and carousels."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM posts WHERE id = %s;", (post_id,))
        post = cursor.fetchone()
        
        # Grab up to 10 images (Instagram's carousel limit)
        cursor.execute("SELECT media_url FROM post_media WHERE post_id = %s LIMIT 10;", (post_id,))
        media_records = cursor.fetchall()
        
        if not media_records:
            raise HTTPException(status_code=400, detail="Instagram requires at least one image.")
            
        title = post['enhanced_title']
        description = post['enhanced_description']
        hashtags = " ".join([f"#{tag}" for tag in post['hashtags']]) if post['hashtags'] else ""
        full_text = f"{title}\n\n{description}\n\n{hashtags}"
        
        system_token = os.environ.get("META_ACCESS_TOKEN")
        ig_id = os.environ.get("INSTAGRAM_ACCOUNT_ID")
        page_id = os.environ.get("FACEBOOK_PAGE_ID")
        page_token = get_page_access_token(system_token, page_id)
        
        if len(media_records) == 1:
            # SINGLE IMAGE
            safe_url = optimize_media_url_for_ig(media_records[0]['media_url'])
            container_url = f"https://graph.facebook.com/v19.0/{ig_id}/media"
            container_payload = {"image_url": safe_url, "caption": full_text, "access_token": page_token}
            cont_response = requests.post(container_url, data=container_payload)
            if cont_response.status_code != 200:
                raise Exception(f"Failed to create IG container: {cont_response.text}")
            creation_id = cont_response.json().get("id")
            
        else:
            # MULTI-IMAGE CAROUSEL
            children_ids = []
            # Step 1: Create an "Item Container" for each image
            for record in media_records:
                safe_url = optimize_media_url_for_ig(record['media_url'])
                item_url = f"https://graph.facebook.com/v19.0/{ig_id}/media"
                item_payload = {"image_url": safe_url, "is_carousel_item": "true", "access_token": page_token}
                item_res = requests.post(item_url, data=item_payload)
                if item_res.status_code == 200:
                    children_ids.append(item_res.json().get("id"))
            
            # Step 2: Group them into a Carousel Container
            carousel_url = f"https://graph.facebook.com/v19.0/{ig_id}/media"
            carousel_payload = {
                "media_type": "CAROUSEL",
                "children": ",".join(children_ids),
                "caption": full_text,
                "access_token": page_token
            }
            car_res = requests.post(carousel_url, data=carousel_payload)
            if car_res.status_code != 200:
                raise Exception(f"Failed to create Carousel: {car_res.text}")
            creation_id = car_res.json().get("id")

        # FINAL STEP: Publish the container (works for both single and carousel)
        publish_url = f"https://graph.facebook.com/v19.0/{ig_id}/media_publish"
        publish_payload = {"creation_id": creation_id, "access_token": page_token}
        pub_response = requests.post(publish_url, data=publish_payload)
        
        if pub_response.status_code != 200:
            raise Exception(f"Failed to publish to IG: {pub_response.text}")
            
        cursor.execute("UPDATE posts SET status = 'Posted' WHERE id = %s;", (post_id,))
        conn.commit()
        return {"message": "Successfully posted to Instagram!"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            cursor.close()
            conn.close()