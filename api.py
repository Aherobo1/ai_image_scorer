from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
import uvicorn
import os
import logging
import json
import base64
import io
import asyncio
from concurrent.futures import ThreadPoolExecutor
from viral_velocity_scorer import ViralVelocityScorer
from image_enhancer import ImageEnhancer
from typing import Optional
from pydantic import BaseModel

# Thread pool for parallel processing
executor = ThreadPoolExecutor(max_workers=15)

# Helper function for parallel scoring
def score_single_image(image_path: str, user_prefs: dict, version: int, skip_moderation: bool = False):
    """Score a single image - used for parallel processing
    
    Args:
        image_path: Path to the image
        user_prefs: User preferences dict
        version: Version number for logging
        skip_moderation: If True, skip content moderation (for pre-moderated enhanced images)
    """
    try:
        score_result = scorer.analyze_image_efficient(image_path, user_prefs, skip_moderation=skip_moderation)
        final_score = round_score(score_result.get('final_score', 0))
        analysis = round_scores_in_dict(score_result)
        return {
            'version': version,
            'final_score': final_score,
            'analysis': analysis,
            'success': True
        }
    except Exception as e:
        logger.error(f"Failed to score image version {version}: {e}")
        return {
            'version': version,
            'final_score': 0.0,
            'analysis': {'error': 'Scoring failed', 'message': str(e)},
            'success': False
        }

async def run_parallel_scoring(images_to_score: list, user_prefs: dict, skip_moderation: bool = False):
    """Run scoring for multiple images in parallel
    
    Args:
        images_to_score: List of image info dicts with 'image_path' and 'version'
        user_prefs: User preferences dict
        skip_moderation: If True, skip content moderation (for pre-moderated enhanced images)
    """
    loop = asyncio.get_event_loop()
    
    # Create tasks for parallel execution
    tasks = []
    for img_info in images_to_score:
        task = loop.run_in_executor(
            executor,
            score_single_image,
            img_info['image_path'],
            user_prefs,
            img_info['version'],
            skip_moderation  # Pass skip_moderation to each scoring task
        )
        tasks.append(task)
    
    # Wait for all tasks to complete
    results = await asyncio.gather(*tasks)
    
    # Create a mapping of version to score result
    score_map = {r['version']: r for r in results}
    return score_map

# Enable HEIC/HEIF support for iPhone images
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_SUPPORT = True
except ImportError:
    HEIC_SUPPORT = False
    print("WARNING: pillow-heif not installed. HEIC images (iPhone) won't be supported.")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('api.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Helper function to round scores to 1 decimal place
def round_score(score):
    """Round score to 1 decimal place for consistent display"""
    if isinstance(score, (int, float)):
        return round(score, 1)
    return score

def round_scores_in_dict(data):
    """Recursively round all numeric scores in a dictionary to 1 decimal place"""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if key in ['score', 'final_score', 'weighted_score'] and isinstance(value, (int, float)):
                result[key] = round_score(value)
            elif isinstance(value, dict):
                result[key] = round_scores_in_dict(value)
            elif isinstance(value, list):
                result[key] = [round_scores_in_dict(item) if isinstance(item, dict) else item for item in value]
            else:
                result[key] = value
        return result
    return data

# Request model
class UserPreferences(BaseModel):
    aesthetic: str = ""
    niche: str = ""
    target_audience: str = ""
    content_type: str = ""
    brand_voice: str = ""
    
    class Config:
        json_schema_extra = {
            "example": {
                "aesthetic": "Minimalist",
                "niche": "Fashion Influencer",
                "target_audience": "Gen Z",
                "content_type": "Instagram Post",
                "brand_voice": "Playful and Trendy"
            }
        }

# Model for individual image with optional score_id
class ImageWithId(BaseModel):
    score_id: Optional[str] = None  # Optional ID for tracking
    image: str  # base64 encoded image
    
    class Config:
        json_schema_extra = {
            "example": {
                "score_id": "upload_123",
                "image": "base64_encoded_image_string_here"
            }
        }

class ScoreImageRequest(BaseModel):
    image: str  # base64 encoded image
    user_preferences: Optional[UserPreferences] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "image": "base64_encoded_image_string_here",
                "user_preferences": {
                    "aesthetic": "Minimalist",
                    "niche": "Fashion Influencer",
                    "target_audience": "Gen Z",
                    "content_type": "Instagram Post",
                    "brand_voice": "Playful and Trendy"
                }
            }
        }

class ScoreImagesRequest(BaseModel):
    images: list  # List of base64 strings OR list of {"score_id": "...", "image": "..."} objects
    user_preferences: Optional[UserPreferences] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "images": [
                    {"score_id": "upload_123", "image": "base64_encoded_image_1"},
                    {"score_id": "upload_456", "image": "base64_encoded_image_2"}
                ],
                "user_preferences": {
                    "aesthetic": "Minimalist",
                    "niche": "Fashion Influencer",
                    "target_audience": "Gen Z",
                    "content_type": "Instagram Post",
                    "brand_voice": "Playful and Trendy"
                }
            }
        }

class EnhanceImageRequest(BaseModel):
    image: str  # base64 encoded image
    user_preferences: Optional[UserPreferences] = None
    num_versions: Optional[int] = 1  # Number of enhanced versions to generate (default: 1, max: 5)
    original_score: Optional[float] = None  # Optional: pre-calculated score to skip re-scoring
    
    class Config:
        json_schema_extra = {
            "example": {
                "image": "base64_encoded_image_string_here",
                "num_versions": 2,
                "original_score": 72.5,
                "user_preferences": {
                    "aesthetic": "Minimalist",
                    "niche": "Fashion Influencer",
                    "target_audience": "Gen Z",
                    "content_type": "Instagram Post",
                    "brand_voice": "Playful and Trendy"
                }
            }
        }

class EnhanceImageCustomRequest(BaseModel):
    image: str  # base64 encoded image (can be original or already enhanced)
    custom_prompt: str  # Required: Custom enhancement instructions from user
    user_preferences: Optional[UserPreferences] = None
    num_versions: Optional[int] = 1  # Number of enhanced versions to generate (default: 1, max: 5)
    
    class Config:
        json_schema_extra = {
            "example": {
                "image": "base64_encoded_image_string_here",
                "custom_prompt": "Make the colors more vibrant and add a subtle warm filter",
                "num_versions": 1,
                "user_preferences": {
                    "aesthetic": "Minimalist",
                    "niche": "Fashion Influencer",
                    "target_audience": "Gen Z",
                    "content_type": "Instagram Post",
                    "brand_voice": "Playful and Trendy"
                }
            }
        }

app = FastAPI(title="ai_image_scorer API", description="AI-powered social media image scoring and enhancement")

# Add general exception handler for all unhandled errors
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"❌ UNHANDLED ERROR for {request.method} {request.url.path}: {type(exc).__name__}: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"}
    )

# Add validation error handler to capture and log Pydantic validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"❌ VALIDATION ERROR for {request.method} {request.url.path}")
    logger.error(f"   Validation errors: {exc.errors()}")
    logger.error(f"   Request body (first 500 chars): {str(exc.body)[:500] if exc.body else 'No body'}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": str(exc.body)[:200] if exc.body else None}
    )

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add middleware to log ALL requests
from starlette.middleware.base import BaseHTTPMiddleware
# Note: Request is imported from fastapi at the top

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger.info(f"📥 INCOMING REQUEST: {request.method} {request.url.path} from {request.client.host if request.client else 'unknown'}")
        logger.info(f"   Content-Type: {request.headers.get('content-type', 'not set')}")
        logger.info(f"   Content-Length: {request.headers.get('content-length', 'not set')}")
        
        try:
            response = await call_next(request)
            logger.info(f"📤 RESPONSE: {response.status_code} for {request.method} {request.url.path}")
            return response
        except Exception as e:
            logger.error(f"❌ REQUEST FAILED: {request.method} {request.url.path} - {str(e)}")
            raise

app.add_middleware(RequestLoggingMiddleware)

# Mount static files (frontend)
if os.path.exists("frontend"):
    app.mount("/static", StaticFiles(directory="frontend"), name="static")

# Initialize the scorer and enhancer
try:
    logger.info("Initializing ViralVelocityScorer for API...")
    scorer = ViralVelocityScorer()
    logger.info("ViralVelocityScorer initialized successfully")
    
    logger.info("Initializing ImageEnhancer for API...")
    enhancer = ImageEnhancer()
    logger.info("ImageEnhancer initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize services: {e}")
    print(f"Failed to initialize services: {e}")
    scorer = None
    enhancer = None

@app.get("/")
def read_root():
    """Serve the main frontend page"""
    logger.info("Root endpoint accessed")
    if os.path.exists("frontend/index.html"):
        return FileResponse("frontend/index.html")
    else:
        return {"message": "ai_image_scorer API - AI-Powered Social Media Image Scorer"}

@app.post("/test-post")
async def test_post(data: dict = None):
    """Simple test endpoint for debugging POST requests"""
    logger.info(f"Test POST received with data: {data}")
    return {"status": "ok", "received": data}

@app.post("/score-image")
async def score_image(request: ScoreImageRequest):
    """
    Score an image using the 4-pillar ai_image_scorer scoring system
    
    Request body:
    {
      "image": "base64 string",
      "user_preferences": {
        "aesthetic": "",
        "niche": "",
        "target_audience": "",
        "content_type": "",
        "brand_voice": ""
      }
    }
    """
    logger.info("Received image scoring request")
    
    if not scorer:
        logger.error("Scorer not initialized, returning 500 error")
        raise HTTPException(status_code=500, detail="Scorer not initialized")
    
    try:
        # Decode base64 image
        logger.info("Decoding base64 image...")
        
        # Debug: Log what we received
        image_base64 = request.image
        logger.info(f"Received image data length: {len(image_base64)} chars")
        logger.info(f"First 100 chars: {image_base64[:100]}")
        
        # Handle data URL prefix (e.g., "data:image/jpeg;base64,...")
        if image_base64.startswith('data:'):
            # Strip the data URL prefix
            if ',' in image_base64:
                image_base64 = image_base64.split(',', 1)[1]
                logger.info("Stripped data URL prefix from base64 string")
            else:
                logger.error("Data URL format but no comma found")
                raise HTTPException(status_code=400, detail="Invalid data URL format")
        
        try:
            image_data = base64.b64decode(image_base64)
            logger.info(f"Decoded image data: {len(image_data)} bytes")
        except Exception as decode_error:
            logger.error(f"Failed to decode base64: {decode_error}")
            raise HTTPException(status_code=400, detail="Invalid base64 image data")
        
        # Validate that we have actual image data
        if len(image_data) < 100:
            logger.error(f"Image data too small: {len(image_data)} bytes")
            raise HTTPException(status_code=400, detail="Image data is too small or empty")
        
        image = io.BytesIO(image_data)
        
        # Verify the image can be opened before saving
        try:
            from PIL import Image as PILImage
            test_img = PILImage.open(io.BytesIO(image_data))
            original_format = test_img.format
            original_mode = test_img.mode
            logger.info(f"Image opened: format={original_format}, mode={original_mode}, size={test_img.size}")
            
            # Convert ANY image to RGB JPEG for consistent processing
            # This handles: PNG (RGBA, P), HEIC, HEIF, WebP, BMP, GIF, etc.
            needs_conversion = (
                original_format in ['HEIF', 'HEIC', 'PNG', 'WEBP', 'GIF', 'BMP', 'TIFF'] or
                original_mode in ('RGBA', 'P', 'LA', 'PA') or
                (original_format is None and HEIC_SUPPORT)
            )
            
            if needs_conversion:
                logger.info(f"Converting {original_format or 'unknown'} format (mode={original_mode}) to RGB JPEG...")
                # Re-open to load the image data (verify() consumes the data)
                test_img = PILImage.open(io.BytesIO(image_data))
                
                # Handle different color modes
                if test_img.mode in ('RGBA', 'LA', 'PA'):
                    # Has alpha channel - composite on white background
                    logger.info(f"Image has alpha channel (mode={test_img.mode}), compositing on white background")
                    background = PILImage.new('RGB', test_img.size, (255, 255, 255))
                    if test_img.mode == 'RGBA':
                        background.paste(test_img, mask=test_img.split()[3])  # Use alpha as mask
                    else:
                        test_img = test_img.convert('RGBA')
                        background.paste(test_img, mask=test_img.split()[3])
                    test_img = background
                elif test_img.mode == 'P':
                    # Palette mode - convert to RGB (or RGBA if has transparency)
                    logger.info(f"Image has palette mode, converting...")
                    if 'transparency' in test_img.info:
                        test_img = test_img.convert('RGBA')
                        background = PILImage.new('RGB', test_img.size, (255, 255, 255))
                        background.paste(test_img, mask=test_img.split()[3])
                        test_img = background
                    else:
                        test_img = test_img.convert('RGB')
                elif test_img.mode != 'RGB':
                    # Any other mode - convert to RGB
                    logger.info(f"Converting mode {test_img.mode} to RGB")
                    test_img = test_img.convert('RGB')
                
                # Save as JPEG to memory
                jpeg_buffer = io.BytesIO()
                test_img.save(jpeg_buffer, format='JPEG', quality=95)
                image_data = jpeg_buffer.getvalue()
                logger.info(f"Converted to JPEG: {len(image_data)} bytes")
            else:
                # JPEG or already compatible format - just verify
                test_img.verify()  # Verify it's a valid image
            logger.info(f"Image validated: format={original_format}, conversion complete")
        except Exception as img_error:
            logger.error(f"Invalid image data: {img_error}")
            raise HTTPException(status_code=400, detail=f"Invalid image file: {str(img_error)}")
        
        # Save temporarily for processing - use unique filename to avoid race conditions
        import uuid
        temp_filename = f"temp_image_{uuid.uuid4().hex[:8]}.jpg"
        with open(temp_filename, "wb") as f:
            f.write(image_data)
        
        logger.info(f"Image decoded and saved temporarily as {temp_filename}")
        
        # Analyze the image
        logger.info("Starting efficient image analysis...")
        user_prefs_dict = request.user_preferences.model_dump() if request.user_preferences else None
        logger.info(f"📋 User preferences received: {user_prefs_dict}")
        result = scorer.analyze_image_efficient(temp_filename, user_prefs_dict)
        
        # Clean up temporary file
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        
        # Handle content moderation rejections specifically
        if result.get('status') == 'rejected':
            logger.warning(f"Content rejected: {result['rejection_reason']}")
            return result
        
        # Handle other errors
        if 'error' in result:
            logger.error(f"Analysis returned error: {result['error']}")
            raise HTTPException(status_code=500, detail=result['error'])
        
        # Round scores in the result for consistent display
        result = round_scores_in_dict(result)
        
        logger.info(f"Analysis completed successfully. Final score: {result.get('final_score', 'N/A')}")
        return result
        
    except Exception as e:
        logger.error(f"Error processing image: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.post("/score-images")
async def score_images(request: ScoreImagesRequest):
    """
    Score multiple images in parallel using the 4-pillar ai_image_scorer scoring system
    
    Request body (Option 1 - simple array of base64 strings):
    {
      "images": ["base64 string 1", "base64 string 2", ...],
      "user_preferences": {...}
    }
    
    Request body (Option 2 - with score_id for tracking):
    {
      "images": [
        {"score_id": "upload_123", "image": "base64 string 1"},
        {"score_id": "upload_456", "image": "base64 string 2"}
      ],
      "user_preferences": {...}
    }
    
    Returns:
    {
      "results": [
        {"index": 0, "score_id": "upload_123", "final_score": 75.5, "definition": {...}, "layout": {...}, "mood": {...}, "vibe_check": {...}},
        {"index": 1, "score_id": "upload_456", "final_score": 82.3, ...},
        ...
      ],
      "total_images": 2,
      "successful": 2,
      "failed": 0
    }
    """
    # Normalize input - support both array of strings and array of objects with score_id
    images = []
    image_ids = {}  # Map index to user-provided score_id
    
    for idx, img_item in enumerate(request.images):
        if isinstance(img_item, str):
            # Simple base64 string
            images.append(img_item)
            image_ids[idx] = None  # No ID provided
        elif isinstance(img_item, dict):
            # Object with score_id and image
            images.append(img_item.get('image', ''))
            image_ids[idx] = img_item.get('score_id', None)
        else:
            logger.warning(f"Invalid image format at index {idx}, skipping")
            continue
    
    logger.info(f"Received batch image scoring request for {len(images)} images")
    
    if not scorer:
        logger.error("Scorer not initialized, returning 500 error")
        raise HTTPException(status_code=500, detail="Scorer not initialized")
    
    if not images or len(images) == 0:
        raise HTTPException(status_code=400, detail="No images provided")
    
    if len(images) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 images allowed per request")
    
    from PIL import Image as PILImage
    import uuid
    
    user_prefs_dict = request.user_preferences.model_dump() if request.user_preferences else None
    
    # Prepare all images for parallel processing
    images_to_score = []
    temp_files = []
    
    for idx, image_base64 in enumerate(images):  # Use normalized images list, not request.images
        try:
            # Handle data URL prefix
            if image_base64.startswith('data:'):
                if ',' in image_base64:
                    image_base64 = image_base64.split(',', 1)[1]
            
            image_data = base64.b64decode(image_base64)
            
            # Validate and convert image
            test_img = PILImage.open(io.BytesIO(image_data))
            original_format = test_img.format
            original_mode = test_img.mode
            
            # Convert to RGB JPEG if needed
            if original_format != 'JPEG' or original_mode != 'RGB':
                test_img = PILImage.open(io.BytesIO(image_data))
                
                if test_img.mode in ('RGBA', 'LA', 'PA'):
                    background = PILImage.new('RGB', test_img.size, (255, 255, 255))
                    if test_img.mode == 'RGBA':
                        background.paste(test_img, mask=test_img.split()[3])
                    else:
                        test_img = test_img.convert('RGBA')
                        background.paste(test_img, mask=test_img.split()[3])
                    test_img = background
                elif test_img.mode == 'P':
                    if 'transparency' in test_img.info:
                        test_img = test_img.convert('RGBA')
                        background = PILImage.new('RGB', test_img.size, (255, 255, 255))
                        background.paste(test_img, mask=test_img.split()[3])
                        test_img = background
                    else:
                        test_img = test_img.convert('RGB')
                elif test_img.mode != 'RGB':
                    test_img = test_img.convert('RGB')
                
                jpeg_buffer = io.BytesIO()
                test_img.save(jpeg_buffer, format='JPEG', quality=95)
                image_data = jpeg_buffer.getvalue()
            
            # Save to temp file
            temp_filename = f"temp_batch_{uuid.uuid4().hex[:8]}.jpg"
            with open(temp_filename, "wb") as f:
                f.write(image_data)
            
            temp_files.append(temp_filename)
            images_to_score.append({
                'image_path': temp_filename,
                'version': idx  # Use index as version for tracking
            })
            logger.info(f"Image {idx} prepared for scoring")
            
        except Exception as e:
            logger.error(f"Failed to prepare image {idx}: {e}")
            images_to_score.append({
                'image_path': None,
                'version': idx,
                'error': str(e)
            })
    
    # Run parallel scoring
    logger.info(f"Starting parallel scoring for {len([i for i in images_to_score if i.get('image_path')])} images...")
    
    # Filter out failed images for scoring
    valid_images = [i for i in images_to_score if i.get('image_path')]
    
    if valid_images:
        score_map = await run_parallel_scoring(valid_images, user_prefs_dict, skip_moderation=False)
    else:
        score_map = {}
    
    # Build results
    results = []
    successful = 0
    failed = 0
    
    for img_info in images_to_score:
        idx = img_info['version']
        score_id = image_ids.get(idx)  # Get user-provided score_id if any
        
        if img_info.get('error'):
            result = {
                'index': idx,
                'status': 'error',
                'error': img_info['error']
            }
            if score_id:
                result['score_id'] = score_id
            results.append(result)
            failed += 1
        else:
            score_result = score_map.get(idx, {})
            if score_result.get('success', False):
                result_data = score_result.get('analysis', {})
                result_data['index'] = idx
                result_data['final_score'] = score_result.get('final_score', 0)
                if score_id:
                    result_data['score_id'] = score_id
                results.append(result_data)
                successful += 1
            else:
                result = {
                    'index': idx,
                    'status': 'error',
                    'error': score_result.get('analysis', {}).get('message', 'Scoring failed')
                }
                if score_id:
                    result['score_id'] = score_id
                results.append(result)
                failed += 1
    
    # Cleanup temp files
    for temp_file in temp_files:
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
    
    # Round scores
    results = [round_scores_in_dict(r) if isinstance(r, dict) else r for r in results]
    
    logger.info(f"Batch scoring completed: {successful} successful, {failed} failed out of {len(images)}")
    
    return {
        'results': results,
        'total_images': len(images),
        'successful': successful,
        'failed': failed
    }

@app.get("/health")
def health_check():
    """Health check endpoint"""
    logger.info("Health check endpoint accessed")
    return {
        "status": "healthy",
        "scorer_initialized": scorer is not None
    }

@app.get("/scoring-weights")
def get_scoring_weights():
    """Get the current scoring weights"""
    logger.info("Scoring weights endpoint accessed")
    
    if not scorer:
        logger.error("Scorer not initialized, returning 500 error")
        raise HTTPException(status_code=500, detail="Scorer not initialized")
    
    return {
        "weights": scorer.weights,
        "description": "4-pillar scoring system weights"
    }

@app.get("/available-preferences")
def get_available_preferences():
    """Get available preference options for users"""
    logger.info("Available preferences endpoint accessed")
    
    return {
        "aesthetics": [
            "Y2K", "Maximalist", "Minimalist", "Ethereal Grunge", 
            "Cottagecore", "Dark Academia", "Cyberpunk", "Vintage",
            "Modern", "Boho", "Streetwear", "High Fashion",
            "Luxury", "Casual", "Professional", "Artistic"
        ],
        "niches": [
            "Fashion Influencer", "Food Blogger", "Travel Photographer",
            "Fitness Influencer", "Tech Professional", "Artist",
            "Business Professional", "Lifestyle Blogger", "Beauty Influencer",
            "Parenting Blogger", "Pet Influencer", "Gaming Content Creator"
        ],
        "target_audiences": [
            "Gen Z", "Millennials", "Gen X", "Boomers",
            "Teenagers", "Young Adults", "Professionals", "Parents",
            "Students", "Entrepreneurs", "Creative Professionals"
        ],
        "content_types": [
            "Instagram Post", "Instagram Story", "TikTok Video",
            "YouTube Thumbnail", "LinkedIn Post", "Twitter Post",
            "Facebook Post", "Pinterest Pin", "Blog Post"
        ],
        "brand_voices": [
            "Playful and Trendy", "Professional and Trustworthy",
            "Casual and Relatable", "Luxury and Sophisticated",
            "Fun and Energetic", "Calm and Minimalist",
            "Bold and Confident", "Warm and Friendly"
        ]
    }

@app.get("/moderation-status")
def get_moderation_status():
    """Get content moderation system status"""
    logger.info("Moderation status endpoint accessed")
    
    if not scorer:
        logger.error("Scorer not initialized, returning 500 error")
        raise HTTPException(status_code=500, detail="Scorer not initialized")
    
    moderation_status = scorer.content_moderator.get_moderation_status()
    return {
        "moderation_system": "Google Cloud Vision SafeSearch",
        "status": moderation_status,
        "description": "Content safety and moderation system for detecting inappropriate content"
    }

@app.post("/enhance-image")
async def enhance_image(request: EnhanceImageRequest):
    """
    Generate enhanced versions of an image using AI (standard enhancement)
    Enhanced images are optimized to score higher than the original.
    
    Request body:
    {
      "image": "base64 string",
      "num_versions": 1,  // Number of enhanced versions to generate (1-5, default: 1)
      "user_preferences": {
        "aesthetic": "",
        "niche": "",
        "target_audience": "",
        "content_type": "",
        "brand_voice": ""
      }
    }
    """
    logger.info(f"Received image enhancement request for {request.num_versions} versions")
    
    if not enhancer:
        logger.error("Enhancer not initialized, returning 500 error")
        raise HTTPException(status_code=500, detail="Enhancer not initialized")
    
    if not scorer:
        logger.error("Scorer not initialized, returning 500 error")
        raise HTTPException(status_code=500, detail="Scorer not initialized")
    
    # Normalize and validate num_versions
    num_versions = request.num_versions if request.num_versions is not None else 1
    if num_versions < 1:
        num_versions = 1
        logger.warning(f"num_versions was less than 1, defaulting to 1")
    elif num_versions > 5:
        logger.error(f"Invalid num_versions: {num_versions} (max is 5)")
        raise HTTPException(status_code=400, detail="num_versions must be between 1 and 5 (max: 5)")
    
    logger.info(f"Will generate {num_versions} enhanced image version(s)")
    
    # Track temp filename for cleanup
    temp_enhance_filename = None
    
    try:
        # Decode base64 image
        logger.info("Decoding base64 image for enhancement...")
        
        # Handle data URL prefix (e.g., "data:image/jpeg;base64,...")
        image_base64 = request.image
        if ',' in image_base64:
            # Strip the data URL prefix
            image_base64 = image_base64.split(',', 1)[1]
            logger.info("Stripped data URL prefix from base64 string")
        
        image_data = base64.b64decode(image_base64)
        
        # Convert image to RGB JPEG for consistent processing (handles PNG, HEIC, WebP, etc.)
        from PIL import Image as PILImage
        test_img = PILImage.open(io.BytesIO(image_data))
        original_format = test_img.format
        original_mode = test_img.mode
        logger.info(f"Enhancement image: format={original_format}, mode={original_mode}")
        
        # Convert to RGB JPEG if needed
        if original_format != 'JPEG' or original_mode != 'RGB':
            logger.info(f"Converting {original_format} (mode={original_mode}) to RGB JPEG for enhancement...")
            test_img = PILImage.open(io.BytesIO(image_data))  # Re-open
            
            if test_img.mode in ('RGBA', 'LA', 'PA'):
                background = PILImage.new('RGB', test_img.size, (255, 255, 255))
                if test_img.mode == 'RGBA':
                    background.paste(test_img, mask=test_img.split()[3])
                else:
                    test_img = test_img.convert('RGBA')
                    background.paste(test_img, mask=test_img.split()[3])
                test_img = background
            elif test_img.mode == 'P':
                if 'transparency' in test_img.info:
                    test_img = test_img.convert('RGBA')
                    background = PILImage.new('RGB', test_img.size, (255, 255, 255))
                    background.paste(test_img, mask=test_img.split()[3])
                    test_img = background
                else:
                    test_img = test_img.convert('RGB')
            elif test_img.mode != 'RGB':
                test_img = test_img.convert('RGB')
            
            jpeg_buffer = io.BytesIO()
            test_img.save(jpeg_buffer, format='JPEG', quality=95)
            image_data = jpeg_buffer.getvalue()
            logger.info(f"Converted to JPEG: {len(image_data)} bytes")
        
        # Save temporarily for processing - use unique filename to avoid race conditions
        import uuid
        temp_enhance_filename = f"temp_enhance_{uuid.uuid4().hex[:8]}.jpg"
        with open(temp_enhance_filename, "wb") as f:
            f.write(image_data)
        
        logger.info(f"Image decoded and saved temporarily as {temp_enhance_filename}")
        
        # Prepare user preferences
        user_prefs_dict = request.user_preferences.model_dump() if request.user_preferences else None
        
        # STEP 1: Score the ORIGINAL image first (for comparison and to guarantee higher scores)
        logger.info("⚡ Scoring original image first...")
        original_score_result = scorer.analyze_image_efficient(temp_enhance_filename, user_prefs_dict)
        original_score = original_score_result.get('final_score', 0)
        logger.info(f"📊 Original image score: {original_score}")
        
        # STEP 2: Generate enhanced images with original score info
        # The enhancer will use this to ensure enhancements score HIGHER
        logger.info(f"Starting AI image enhancement for {num_versions} version(s)...")
        result = enhancer.enhance_image(
            temp_enhance_filename, 
            user_prefs_dict, 
            num_versions=num_versions,
            custom_prompt=None,  # No custom prompt for standard enhancement
            original_score=original_score  # Pass original score to guarantee improvement
        )
        
        # Clean up temporary file
        if os.path.exists(temp_enhance_filename):
            os.remove(temp_enhance_filename)
        
        if result['status'] == 'error':
            logger.error(f"Enhancement failed: {result['error']}")
            raise HTTPException(status_code=500, detail=result['error'])
        
        # Check if any enhanced images were generated
        if not result['enhanced_images'] or len(result['enhanced_images']) == 0:
            logger.error("No enhanced images were generated by Gemini")
            raise HTTPException(
                status_code=500, 
                detail="AI enhancement service temporarily unavailable. Please try again in a moment."
            )
        
        # Round scores in the result for consistent display
        result = round_scores_in_dict(result)
        
        logger.info(f"Enhancement completed successfully. Generated {result['total_generated']} images")
        
        # Prepare images for parallel scoring
        images_to_score = []
        image_base64_map = {}
        
        for enhanced_img in result['enhanced_images']:
            try:
                with open(enhanced_img['image_path'], 'rb') as f:
                    img_data = f.read()
                    img_base64 = base64.b64encode(img_data).decode()
                
                images_to_score.append({
                    'image_path': enhanced_img['image_path'],
                    'version': enhanced_img['version'],
                    'prompt': enhanced_img['prompt']
                })
                image_base64_map[enhanced_img['version']] = img_base64
            except Exception as e:
                logger.error(f"Failed to read enhanced image {enhanced_img['version']}: {e}")
        
        # Run parallel scoring for all enhanced images
        # OPTIMIZATION: Skip moderation for enhanced images (original was already moderated)
        logger.info(f"Starting parallel scoring for {len(images_to_score)} enhanced images...")
        score_map = await run_parallel_scoring(images_to_score, user_prefs_dict, skip_moderation=True)
        logger.info(f"Parallel scoring completed for {len(score_map)} images")
        
        # Combine results
        enhanced_images_data = []
        for img_info in images_to_score:
            version = img_info['version']
            score_result = score_map.get(version, {})
            
            enhanced_images_data.append({
                'version': version,
                'image': image_base64_map.get(version, ''),
                'prompt': img_info['prompt'],
                'image_path': img_info['image_path'],
                'score': score_result.get('final_score', 0),
                'analysis': score_result.get('analysis', {'error': 'Scoring not available'})
            })
        
        logger.info(f"Processed {len(enhanced_images_data)} out of {result['total_generated']} generated images")
        
        # Log score improvements for verification
        for enhanced_img in enhanced_images_data:
            enhanced_score = enhanced_img.get('score', 0)
            improvement = enhanced_score - original_score
            logger.info(f"📊 Version {enhanced_img['version']}: {original_score} -> {enhanced_score} ({'+' if improvement >= 0 else ''}{improvement:.1f})")
        
        return {
            'status': 'success',
            'message': f'Successfully generated {len(enhanced_images_data)} enhanced images',
            'enhanced_images': enhanced_images_data,
            'total_generated': len(enhanced_images_data),
            'original_score': original_score,  # Include original score for transparency
            'original_analysis': result['original_image']['analysis']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing enhancement request: {str(e)}", exc_info=True)
        # Clean up temporary file on error
        if temp_enhance_filename and os.path.exists(temp_enhance_filename):
            os.remove(temp_enhance_filename)
        raise HTTPException(status_code=500, detail=f"Enhancement failed: {str(e)}")

@app.post("/custom-prompt")
async def custom_prompt_enhancement(request: EnhanceImageCustomRequest):
    """
    Generate enhanced versions of an image using AI with custom prompt
    Works with both ordinary photos AND already enhanced photos
    
    Request body:
    {
      "image": "base64 string",  // Can be original or already enhanced image
      "custom_prompt": "Make colors more vibrant",  // Required
      "num_versions": 1,  // Number of enhanced versions to generate (1-5, default: 1)
      "user_preferences": {
        "aesthetic": "",
        "niche": "",
        "target_audience": "",
        "content_type": "",
        "brand_voice": ""
      }
    }
    """
    logger.info(f"Received custom prompt enhancement request for {request.num_versions} versions")
    logger.info(f"Custom prompt: {request.custom_prompt[:100]}...")
    
    if not enhancer:
        logger.error("Enhancer not initialized, returning 500 error")
        raise HTTPException(status_code=500, detail="Enhancer not initialized")
    
    if not scorer:
        logger.error("Scorer not initialized, returning 500 error")
        raise HTTPException(status_code=500, detail="Scorer not initialized")
    
    # Validate custom_prompt is provided
    if not request.custom_prompt or not request.custom_prompt.strip():
        logger.error("Custom prompt is required but was empty")
        raise HTTPException(status_code=400, detail="custom_prompt is required and cannot be empty")
    
    # Normalize and validate num_versions
    num_versions = request.num_versions if request.num_versions is not None else 1
    if num_versions < 1:
        num_versions = 1
        logger.warning(f"num_versions was less than 1, defaulting to 1")
    elif num_versions > 5:
        logger.error(f"Invalid num_versions: {num_versions} (max is 5)")
        raise HTTPException(status_code=400, detail="num_versions must be between 1 and 5 (max: 5)")
    
    logger.info(f"Will generate {num_versions} custom enhanced image version(s)")
    
    # Track temp filename for cleanup
    temp_custom_filename = None
    
    try:
        # Decode base64 image
        logger.info("Decoding base64 image for custom enhancement...")
        
        # Handle data URL prefix (e.g., "data:image/jpeg;base64,...")
        image_base64 = request.image
        if ',' in image_base64:
            # Strip the data URL prefix
            image_base64 = image_base64.split(',', 1)[1]
            logger.info("Stripped data URL prefix from base64 string")
        
        image_data = base64.b64decode(image_base64)
        
        # Convert image to RGB JPEG for consistent processing (handles PNG, HEIC, WebP, etc.)
        from PIL import Image as PILImage
        test_img = PILImage.open(io.BytesIO(image_data))
        original_format = test_img.format
        original_mode = test_img.mode
        logger.info(f"Custom enhancement image: format={original_format}, mode={original_mode}")
        
        # Convert to RGB JPEG if needed
        if original_format != 'JPEG' or original_mode != 'RGB':
            logger.info(f"Converting {original_format} (mode={original_mode}) to RGB JPEG for custom enhancement...")
            test_img = PILImage.open(io.BytesIO(image_data))  # Re-open
            
            if test_img.mode in ('RGBA', 'LA', 'PA'):
                background = PILImage.new('RGB', test_img.size, (255, 255, 255))
                if test_img.mode == 'RGBA':
                    background.paste(test_img, mask=test_img.split()[3])
                else:
                    test_img = test_img.convert('RGBA')
                    background.paste(test_img, mask=test_img.split()[3])
                test_img = background
            elif test_img.mode == 'P':
                if 'transparency' in test_img.info:
                    test_img = test_img.convert('RGBA')
                    background = PILImage.new('RGB', test_img.size, (255, 255, 255))
                    background.paste(test_img, mask=test_img.split()[3])
                    test_img = background
                else:
                    test_img = test_img.convert('RGB')
            elif test_img.mode != 'RGB':
                test_img = test_img.convert('RGB')
            
            jpeg_buffer = io.BytesIO()
            test_img.save(jpeg_buffer, format='JPEG', quality=95)
            image_data = jpeg_buffer.getvalue()
            logger.info(f"Converted to JPEG: {len(image_data)} bytes")
        
        # Save temporarily for processing - use unique filename to avoid race conditions
        import uuid
        temp_custom_filename = f"temp_custom_{uuid.uuid4().hex[:8]}.jpg"
        with open(temp_custom_filename, "wb") as f:
            f.write(image_data)
        
        logger.info(f"Image decoded and saved temporarily as {temp_custom_filename}")
        
        # Prepare user preferences
        user_prefs_dict = request.user_preferences.model_dump() if request.user_preferences else None
        
        # Generate enhanced images WITH custom prompt
        logger.info(f"Starting AI image enhancement with custom prompt for {num_versions} version(s)...")
        result = enhancer.enhance_image(
            temp_custom_filename, 
            user_prefs_dict, 
            num_versions=num_versions,
            custom_prompt=request.custom_prompt
        )
        
        # Clean up temporary file
        if os.path.exists(temp_custom_filename):
            os.remove(temp_custom_filename)
        
        if result['status'] == 'error':
            logger.error(f"Custom enhancement failed: {result['error']}")
            raise HTTPException(status_code=500, detail=result['error'])
        
        # Check if any enhanced images were generated
        if not result['enhanced_images'] or len(result['enhanced_images']) == 0:
            logger.error("No custom enhanced images were generated by Gemini")
            raise HTTPException(
                status_code=500, 
                detail="AI enhancement service temporarily unavailable. Please try again in a moment."
            )
        
        # Round scores in the result for consistent display
        result = round_scores_in_dict(result)
        
        logger.info(f"Custom enhancement completed successfully. Generated {result['total_generated']} images")
        
        # Prepare images for parallel scoring
        images_to_score = []
        image_base64_map = {}
        
        for enhanced_img in result['enhanced_images']:
            try:
                with open(enhanced_img['image_path'], 'rb') as f:
                    img_data = f.read()
                    img_base64 = base64.b64encode(img_data).decode()
                
                images_to_score.append({
                    'image_path': enhanced_img['image_path'],
                    'version': enhanced_img['version'],
                    'prompt': enhanced_img['prompt']
                })
                image_base64_map[enhanced_img['version']] = img_base64
            except Exception as e:
                logger.error(f"Failed to read custom enhanced image {enhanced_img['version']}: {e}")
        
        # Run parallel scoring for all enhanced images
        # OPTIMIZATION: Skip moderation for enhanced images (original was already moderated)
        logger.info(f"Starting parallel scoring for {len(images_to_score)} custom enhanced images...")
        score_map = await run_parallel_scoring(images_to_score, user_prefs_dict, skip_moderation=True)
        logger.info(f"Parallel scoring completed for {len(score_map)} custom enhanced images")
        
        # Combine results
        enhanced_images_data = []
        for img_info in images_to_score:
            version = img_info['version']
            score_result = score_map.get(version, {})
            
            enhanced_images_data.append({
                'version': version,
                'image': image_base64_map.get(version, ''),
                'prompt': img_info['prompt'],
                'image_path': img_info['image_path'],
                'score': score_result.get('final_score', 0),
                'analysis': score_result.get('analysis', {'error': 'Scoring not available'}),
                'custom_prompt': request.custom_prompt
            })
        
        logger.info(f"Processed {len(enhanced_images_data)} out of {result['total_generated']} custom enhanced images")
        
        return {
            'status': 'success',
            'message': f'Successfully generated {len(enhanced_images_data)} custom enhanced images',
            'enhanced_images': enhanced_images_data,
            'total_generated': len(enhanced_images_data),
            'original_analysis': result['original_image']['analysis'],
            'custom_prompt_used': request.custom_prompt
        }
        
    except Exception as e:
        logger.error(f"Error processing custom enhancement request: {str(e)}", exc_info=True)
        # Clean up temporary file on error
        if temp_custom_filename and os.path.exists(temp_custom_filename):
            os.remove(temp_custom_filename)
        raise HTTPException(status_code=500, detail=f"Custom enhancement failed: {str(e)}")

if __name__ == "__main__":
    logger.info("Starting ai_image_scorer API server...")
    # Increased timeout and body limit to support large base64 images (up to 50MB)
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=5300, 
        limit_concurrency=100, 
        limit_max_requests=None,
        timeout_keep_alive=120,  # Keep connection alive for 2 minutes
        h11_max_incomplete_event_size=50 * 1024 * 1024,  # 50MB for large images
    )
