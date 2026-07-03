import os
import base64
import json
import logging
from typing import Dict, List, Optional, Tuple
import google.generativeai as genai
from PIL import Image, ImageOps
import io
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('image_enhancer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ImageEnhancer:
    """
    AI Image Enhancement using Google Gemini 2.5 Flash Image
    Generates enhanced versions of uploaded images using true AI editing
    """
    
    def __init__(self):
        """Initialize the image enhancer with Gemini 2.5 Flash Image"""
        logger.info("Initializing ImageEnhancer with Gemini 2.5 Flash Image...")
        
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            logger.error("GEMINI_API_KEY not found in environment variables")
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        logger.info("Gemini API key found, initializing client...")
        genai.configure(api_key=api_key)
        
        # Use gemini-2.5-flash-image for IMAGE EDITING (billing now enabled!)
        try:
            # Primary: gemini-2.5-flash-image for true AI image editing
            self.image_model = genai.GenerativeModel('gemini-2.5-flash-image')
            logger.info("✅ Using gemini-2.5-flash-image for AI image editing (billing ACTIVE)")
        except Exception as e:
            logger.warning(f"Failed to initialize gemini-2.5-flash-image: {e}")
            self.image_model = None
        
        # Use the same model for analysis (gemini-2.5-flash-image works for both)
        # This avoids issues with gemini-2.5-flash returning empty responses
        self.model = self.image_model if self.image_model else None
        if self.model:
            logger.info("Using gemini-2.5-flash-image for image analysis too")
        else:
            # Fallback to gemini-2.5-flash if image model not available
            try:
                self.model = genai.GenerativeModel('gemini-2.5-flash')
                logger.info("Using gemini-2.5-flash for image analysis")
            except Exception as e:
                logger.warning(f"Failed to initialize gemini-2.5-flash: {e}")
                try:
                    self.model = genai.GenerativeModel('gemini-2.0-flash')
                    logger.info("Using gemini-2.0-flash for image analysis")
                except Exception as e2:
                    logger.error(f"Failed to initialize any Gemini model: {e2}")
                    raise e2
        
        logger.info("ImageEnhancer initialization complete")
    
    def enhance_image(self, image_path: str, user_preferences: Optional[Dict] = None, num_versions: int = 1, custom_prompt: Optional[str] = None, original_score: Optional[float] = None) -> Dict:
        """
        Generate enhanced versions of an image
        
        Args:
            image_path: Path to the original image
            user_preferences: User preferences for enhancement style
            num_versions: Number of enhanced versions to generate (1-5, default: 1)
            custom_prompt: Custom enhancement instructions from user
            original_score: Original image's score (used to guarantee higher scores for auto-enhancement)
            
        Returns:
            Dict containing enhanced images and metadata
        """
        # Validate and normalize num_versions
        if num_versions is None or num_versions < 1:
            num_versions = 1
        elif num_versions > 5:
            logger.warning(f"num_versions {num_versions} exceeds maximum of 5, capping at 5")
            num_versions = 5
            
        if custom_prompt:
            logger.info(f"Starting image enhancement with custom prompt: {custom_prompt[:100]}...")
        else:
            logger.info(f"Starting image enhancement for: {image_path} (generating {num_versions} versions)")
            if original_score:
                logger.info(f"📊 Original score: {original_score} - enhancements will target HIGHER scores")
        
        try:
            # Load original image
            original_image = Image.open(image_path)
            logger.info(f"Original image loaded. Size: {original_image.size}, Mode: {original_image.mode}")
            
            # Fix image orientation based on EXIF data
            original_image = self._fix_image_orientation(original_image)
            
            # Analyze original image to understand what needs enhancement
            # OPTIMIZATION: Skip analysis if custom prompt is provided (saves ~2-3 sec)
            if custom_prompt:
                logger.info("⚡ Skipping image analysis - using custom prompt directly")
                analysis = {
                    "issues_found": ["custom enhancement requested"],
                    "enhancement_priorities": [custom_prompt],
                    "overall_quality": "unknown",
                    "main_subject": "as specified by user",
                    "background": "as specified by user",
                    "lighting": "as specified by user"
                }
            else:
                analysis = self._analyze_image_for_enhancement(original_image)
                logger.info(f"Image analysis complete: {analysis['issues_found']}")
            
            # Generate enhancement prompts based on analysis, user preferences, and custom prompt
            enhancement_prompts = self._generate_enhancement_prompts(analysis, user_preferences, num_versions, custom_prompt, original_score)
            logger.info(f"Generated {len(enhancement_prompts)} enhancement prompts")
            
            # OPTIMIZATION: Generate enhanced images IN PARALLEL (saves ~9 sec per additional image)
            if num_versions > 1:
                logger.info(f"⚡ Using PARALLEL enhancement for {num_versions} versions...")
                enhanced_images = self._generate_enhanced_images_parallel(original_image, enhancement_prompts)
            else:
                # Single image - no need for parallelization
                enhanced_images = []
                for i, prompt in enumerate(enhancement_prompts):
                    logger.info(f"Generating enhanced image {i+1}/{num_versions}...")
                    enhanced_image = self._generate_enhanced_image(original_image, prompt, i+1)
                    if enhanced_image:
                        enhanced_images.append(enhanced_image)
                    else:
                        logger.warning(f"Generation failed for version {i+1}, creating placeholder...")
                        placeholder = self._create_enhanced_placeholder(original_image, prompt, i+1)
                        if placeholder:
                            enhanced_images.append(placeholder)
            
            logger.info(f"Successfully generated {len(enhanced_images)} enhanced images (requested: {num_versions})")
            
            # Warn if we didn't get all requested versions
            if len(enhanced_images) < num_versions:
                logger.warning(f"Only generated {len(enhanced_images)} out of {num_versions} requested enhanced images")
            
            return {
                'status': 'success',
                'original_image': {
                    'path': image_path,
                    'size': original_image.size,
                    'analysis': analysis
                },
                'enhanced_images': enhanced_images,
                'total_generated': len(enhanced_images),
                'enhancement_prompts': enhancement_prompts
            }
            
        except Exception as e:
            logger.error(f"Image enhancement failed: {str(e)}", exc_info=True)
            return {
                'status': 'error',
                'error': f'Enhancement failed: {str(e)}',
                'enhanced_images': []
            }
    
    def _generate_enhanced_images_parallel(self, original_image: Image, enhancement_prompts: List[str]) -> List[Dict]:
        """
        Generate multiple enhanced images in PARALLEL using ThreadPoolExecutor
        This significantly speeds up multi-version enhancement requests
        """
        import time
        start_time = time.time()
        num_versions = len(enhancement_prompts)
        logger.info(f"⚡ Starting PARALLEL enhancement for {num_versions} versions...")
        
        def enhance_single(args):
            prompt, version = args
            try:
                logger.info(f"[Parallel] Generating version {version}...")
                result = self._generate_enhanced_image(original_image, prompt, version)
                if result:
                    return result
                else:
                    logger.warning(f"[Parallel] Generation failed for version {version}, creating placeholder...")
                    return self._create_enhanced_placeholder(original_image, prompt, version)
            except Exception as e:
                logger.error(f"[Parallel] Error generating version {version}: {e}")
                return None
        
        # Create list of (prompt, version) tuples
        tasks = [(prompt, i+1) for i, prompt in enumerate(enhancement_prompts)]
        
        # Use ThreadPoolExecutor for parallel execution
        enhanced_images = []
        with ThreadPoolExecutor(max_workers=min(num_versions, 5)) as executor:
            results = list(executor.map(enhance_single, tasks))
            enhanced_images = [r for r in results if r is not None]
        
        elapsed = time.time() - start_time
        logger.info(f"⚡ PARALLEL enhancement complete: {len(enhanced_images)} images in {elapsed:.1f}s")
        
        return enhanced_images

    def _analyze_image_for_enhancement(self, image: Image) -> Dict:
        """
        Analyze image to identify enhancement opportunities
        """
        logger.info("Analyzing image for enhancement opportunities...")
        
        prompt = """
        Analyze this image and identify specific issues that could be improved for social media.
        Focus on technical and compositional issues that can be enhanced without changing personal appearance.
        
        Look for:
        1. Blurry or out-of-focus areas
        2. Closed eyes in group photos
        3. Unwanted objects (fingers, passing people, etc.)
        4. Poor lighting or exposure
        5. Composition issues
        6. Color balance problems
        7. Noise or grain
        8. Cropping opportunities
        
        Return ONLY a JSON object with:
        {
            "issues_found": ["list of specific issues"],
            "enhancement_priorities": ["ordered list of what to fix first"],
            "overall_quality": "good/medium/poor",
            "main_subject": "description of main subject",
            "background": "description of background",
            "lighting": "description of lighting conditions"
        }
        """
        
        try:
            response = self._get_gemini_response(image, prompt)
            analysis = json.loads(self._clean_json_response(response))
            logger.info(f"Image analysis: {analysis['issues_found']} issues found")
            return analysis
        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            return {
                "issues_found": ["general enhancement needed"],
                "enhancement_priorities": ["improve overall quality"],
                "overall_quality": "medium",
                "main_subject": "person or object",
                "background": "various",
                "lighting": "mixed"
            }
    
    def _generate_enhancement_prompts(self, analysis: Dict, user_preferences: Optional[Dict] = None, num_versions: int = 5, custom_prompt: Optional[str] = None, original_score: Optional[float] = None) -> List[str]:
        """
        Generate enhancement prompts focused on IMPROVING image quality to get HIGHER scores
        
        Args:
            analysis: Image analysis results
            user_preferences: User preferences for enhancement style
            num_versions: Number of prompts to generate (1-5)
            custom_prompt: Custom enhancement instructions from user
        """
        logger.info(f"Generating {num_versions} enhancement prompts...")
        
        # Build score improvement target text for auto-enhancement
        score_target_text = ""
        if original_score and not custom_prompt:
            if original_score < 50:
                improvement = "+20 points"
            elif original_score < 70:
                improvement = "+15 points"
            elif original_score < 85:
                improvement = "+10 points"
            else:
                improvement = "+5 points"
            score_target_text = f"The original image scores {original_score}/100. Your enhancement MUST improve this score by at least {improvement}. "
            logger.info(f"📊 Score target: improve from {original_score} by {improvement}")
        
        # If user provided a custom prompt, prioritize it
        if custom_prompt:
            logger.info(f"Using custom prompt: {custom_prompt}")
        
        issues = analysis.get('issues_found', [])
        priorities = analysis.get('enhancement_priorities', [])
        
        # Enhancement focuses designed to IMPROVE quality scores
        # Each focuses on different scoring criteria to maximize score improvement
        enhancement_focuses = [
            # Version 1: Focus on Definition (Technical Quality) - sharpness, clarity, noise reduction
            "IMPROVE image sharpness and clarity significantly. Reduce any noise or grain. Enhance resolution and detail. Make the image look crisp and professional quality.",
            
            # Version 2: Focus on Layout (Compositional Strength) - balance, framing, visual flow
            "IMPROVE the visual balance and composition. Enhance the framing and visual flow. Make the subject stand out more clearly. Improve depth perception.",
            
            # Version 3: Focus on Mood (Psychological Engagement) - colors, emotion, atmosphere
            "IMPROVE the emotional impact and mood of the image. Enhance color vibrancy and warmth. Make the image more engaging and emotionally appealing. Improve the overall atmosphere.",
            
            # Version 4: Focus on Vibe Check (Trend & Zeitgeist) - modern aesthetic, social media appeal
            "IMPROVE the modern aesthetic appeal. Make the image look more polished and social-media ready. Enhance the contemporary look while keeping it authentic.",
            
            # Version 5: Balanced improvement across all areas
            "IMPROVE overall image quality comprehensively. Enhance sharpness, colors, lighting, and composition. Make the image look significantly better and more professional."
        ]
        
        # Only use the number of focuses requested
        enhancement_focuses = enhancement_focuses[:num_versions]
        
        prompts = []
        for i, focus in enumerate(enhancement_focuses):
            # Create specific enhancement prompt focused on IMPROVEMENT
            prompt = f"{score_target_text}{focus} "
            
            # Add specific fixes based on analysis
            if issues:
                specific_fixes = []
                for issue in issues[:3]:  # Focus on top 3 issues
                    if 'blur' in issue.lower() or 'focus' in issue.lower():
                        specific_fixes.append("significantly sharpen the image")
                    elif 'light' in issue.lower() or 'exposure' in issue.lower():
                        specific_fixes.append("optimize lighting and exposure")
                    elif 'color' in issue.lower():
                        specific_fixes.append("enhance color vibrancy and balance")
                    elif 'noise' in issue.lower():
                        specific_fixes.append("reduce noise while keeping detail")
                    elif 'contrast' in issue.lower():
                        specific_fixes.append("improve contrast")
                
                if specific_fixes:
                    prompt += "Also: " + ", ".join(specific_fixes) + ". "
            
            # Add custom prompt if provided by user
            if custom_prompt:
                prompt += f"USER SPECIFIC REQUEST: {custom_prompt}. "
                logger.info(f"Added custom prompt to version {i+1}: {custom_prompt}")
            
            # Critical instructions: Improve quality while preserving subject
            if original_score and not custom_prompt:
                prompt += f"CRITICAL: The enhanced image MUST score HIGHER than {original_score}/100. "
            prompt += "REQUIREMENTS: 1) The enhanced image MUST look noticeably BETTER than the original. 2) Keep the same subject, people, and basic composition. 3) Do NOT alter faces, body shapes, or personal appearance. 4) Focus on technical improvements: sharpness, colors, lighting, clarity. 5) The result should score HIGHER on image quality metrics."
            
            prompts.append(prompt)
        
        logger.info(f"Generated {len(prompts)} enhancement prompts focused on IMPROVING quality")
        return prompts
    
    def _generate_enhanced_image(self, original_image: Image, prompt: str, version: int) -> Optional[Dict]:
        """
        Generate a single enhanced image using Gemini 2.5 Flash Image (true AI editing)
        """
        try:
            logger.info(f"Generating enhanced image version {version} with Gemini 2.5 Flash Image...")
            
            # Check if image model is available
            if not hasattr(self, 'image_model') or self.image_model is None:
                logger.warning("Image model not available, using PIL fallback")
                return self._create_enhanced_placeholder(original_image, prompt, version)
            
            # Prepare the image for Gemini
            img_buffer = io.BytesIO()
            original_image.save(img_buffer, format='JPEG', quality=95)
            img_buffer.seek(0)
            img_bytes = img_buffer.getvalue()
            
            # Create editing instruction for Gemini
            edit_instruction = f"""ENHANCE and IMPROVE this image with the following instructions:
{prompt}

GOAL: Make this image look SIGNIFICANTLY BETTER than the original.

IMPORTANT: 
- IMPROVE sharpness, clarity, colors, lighting, and overall quality
- Keep the original subject, people, and composition intact
- Do NOT change faces, body shapes, or add/remove people
- The enhanced image must look MORE professional and higher quality
- Return the IMPROVED image"""
            
            logger.info(f"Sending image to Gemini 2.5 Flash Image for editing...")
            
            # Send image + edit instruction to Gemini 2.5 Flash Image
            try:
                response = self.image_model.generate_content([
                    {"mime_type": "image/jpeg", "data": img_bytes},
                    edit_instruction
                ])
            except Exception as e:
                logger.error(f"Gemini image generation failed: {e}")
                return self._create_enhanced_placeholder(original_image, prompt, version)
            
            # Log the response structure for debugging
            logger.info(f"Response type: {type(response)}")
            logger.info(f"Response parts: {len(response.parts) if hasattr(response, 'parts') else 'No parts'}")
            
            # Check if response contains an edited image
            if hasattr(response, 'parts') and response.parts:
                for i, part in enumerate(response.parts):
                    # Check for inline_data (image data)
                    if hasattr(part, 'inline_data') and part.inline_data:
                        logger.info(f"✅ Gemini returned edited image for version {version}")
                        enhanced_image_path = self._save_gemini_image(part.inline_data.data, version)
                        
                        if enhanced_image_path:
                            logger.info(f"✅ Enhanced image {version} saved to: {enhanced_image_path}")
                            return {
                                'version': version,
                                'prompt': prompt,
                                'image_path': enhanced_image_path,
                                'generation_method': 'gemini-2.5-flash-image'
                            }
            
            # If no image was returned, fall back to PIL enhancement
            logger.warning(f"Gemini didn't return edited image for version {version}, using PIL fallback...")
            return self._create_enhanced_placeholder(original_image, prompt, version)
                
        except Exception as e:
            logger.error(f"Failed to generate enhanced image {version}: {e}", exc_info=True)
            # Try to create a placeholder as last resort
            try:
                logger.info(f"Attempting to create placeholder for version {version} after error...")
                return self._create_enhanced_placeholder(original_image, prompt, version)
            except Exception as e2:
                logger.error(f"Failed to create placeholder for version {version}: {e2}", exc_info=True)
                return None
    
    def _save_gemini_image(self, image_data: bytes, version: int) -> Optional[str]:
        """
        Save Gemini generated image to local storage
        """
        try:
            # Create enhanced images directory
            enhanced_dir = "enhanced_images"
            os.makedirs(enhanced_dir, exist_ok=True)
            
            # Generate unique filename
            filename = f"enhanced_v{version}_{uuid.uuid4().hex[:8]}.jpg"
            filepath = os.path.join(enhanced_dir, filename)
            
            # Save image data directly
            with open(filepath, 'wb') as f:
                f.write(image_data)
            
            logger.info(f"Gemini enhanced image {version} saved to: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Failed to save Gemini image: {e}")
            return None
    
    def _create_enhanced_placeholder(self, original_image: Image, prompt: str, version: int, instructions: str = None) -> Optional[Dict]:
        """
        Create a placeholder enhanced image when Gemini doesn't generate images
        This applies basic image processing to simulate enhancement
        """
        try:
            logger.info(f"Creating enhanced placeholder for version {version}...")
            
            # Create enhanced images directory
            enhanced_dir = "enhanced_images"
            os.makedirs(enhanced_dir, exist_ok=True)
            
            # Generate unique filename
            filename = f"enhanced_v{version}_{uuid.uuid4().hex[:8]}.jpg"
            filepath = os.path.join(enhanced_dir, filename)
            
            # Apply basic enhancements to simulate AI enhancement
            enhanced_image = original_image.copy()
            
            # FIX: Use MORE AGGRESSIVE enhancement factors to actually IMPROVE quality
            # Increased from subtle 1.02-1.05x to noticeable 1.08-1.15x for real improvements
            enhancement_factors = {
                1: {'brightness': 1.08, 'contrast': 1.12, 'color': 1.08, 'sharpness': 1.15},  # Definition focus
                2: {'brightness': 1.05, 'contrast': 1.15, 'color': 1.05, 'sharpness': 1.10},  # Layout focus
                3: {'brightness': 1.10, 'contrast': 1.08, 'color': 1.15, 'sharpness': 1.08},  # Mood focus
                4: {'brightness': 1.08, 'contrast': 1.10, 'color': 1.12, 'sharpness': 1.12},  # Vibe focus
                5: {'brightness': 1.10, 'contrast': 1.12, 'color': 1.10, 'sharpness': 1.15}   # Balanced
            }
            
            factors = enhancement_factors.get(version, enhancement_factors[1])
            
            logger.info(f"Using QUALITY-IMPROVING enhancement factors for version {version}: {factors}")
            
            # Apply enhancements
            from PIL import ImageEnhance, ImageFilter
            
            # Brightness
            if factors['brightness'] != 1.0:
                enhancer = ImageEnhance.Brightness(enhanced_image)
                enhanced_image = enhancer.enhance(factors['brightness'])
            
            # Contrast
            if factors['contrast'] != 1.0:
                enhancer = ImageEnhance.Contrast(enhanced_image)
                enhanced_image = enhancer.enhance(factors['contrast'])
            
            # Color/Saturation
            if factors['color'] != 1.0:
                enhancer = ImageEnhance.Color(enhanced_image)
                enhanced_image = enhancer.enhance(factors['color'])
            
            # Sharpness - use Sharpness enhancer for more control
            if factors['sharpness'] and factors['sharpness'] != 1.0:
                enhancer = ImageEnhance.Sharpness(enhanced_image)
                enhanced_image = enhancer.enhance(factors['sharpness'])
            
            # Apply additional enhancements based on prompt keywords
            if "sharp" in prompt.lower() or "clarity" in prompt.lower() or "crisp" in prompt.lower():
                enhancer = ImageEnhance.Sharpness(enhanced_image)
                enhanced_image = enhancer.enhance(1.2)  # Extra sharpening
            
            if "vibrant" in prompt.lower() or "color" in prompt.lower():
                enhancer = ImageEnhance.Color(enhanced_image)
                enhanced_image = enhancer.enhance(1.15)  # Extra color boost
            
            if "bright" in prompt.lower() or "light" in prompt.lower():
                enhancer = ImageEnhance.Brightness(enhanced_image)
                enhanced_image = enhancer.enhance(1.08)
            
            # FIX: Apply orientation correction before saving to prevent rotation issues
            enhanced_image = ImageOps.exif_transpose(enhanced_image)
            
            # Save the enhanced image with EXIF data preserved
            try:
                # Try to preserve original EXIF data
                exif_data = original_image.info.get('exif')
                if exif_data:
                    enhanced_image.save(filepath, 'JPEG', quality=95, exif=exif_data)
                    logger.info(f"Saved with original EXIF data preserved")
                else:
                    enhanced_image.save(filepath, 'JPEG', quality=95)
                    logger.info(f"Saved without EXIF data (original had none)")
            except Exception as save_error:
                # Fallback: save without EXIF if it fails
                logger.warning(f"Could not save with EXIF, saving without: {save_error}")
                enhanced_image.save(filepath, 'JPEG', quality=95)
            
            logger.info(f"Enhanced placeholder {version} saved successfully to: {filepath}")
            
            result = {
                'version': version,
                'prompt': prompt,
                'image_path': filepath,
                'generation_method': 'ai-enhanced-placeholder',
                'enhancement_factors': factors,
                'gemini_instructions': instructions[:200] if instructions else None
            }
            
            logger.info(f"Returning placeholder result for version {version}: {result['generation_method']}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to create enhanced placeholder {version}: {e}", exc_info=True)
            return None
    
    def _get_gemini_response(self, image: Image, prompt: str) -> str:
        """Get response from Gemini for image analysis"""
        try:
            # Prepare the image for Gemini
            img_buffer = io.BytesIO()
            image.save(img_buffer, format='JPEG')
            img_buffer.seek(0)
            
            # Create the content for Gemini (image + text prompt)
            content = [
                {
                    "mime_type": "image/jpeg",
                    "data": img_buffer.getvalue()
                },
                prompt
            ]
            
            # Get response from Gemini
            response = self.model.generate_content(content)
            
            # Check if response has valid parts
            if hasattr(response, 'parts') and response.parts:
                # Try to get text from the first part
                for part in response.parts:
                    if hasattr(part, 'text') and part.text:
                        return part.text
            
            # Try response.text as fallback (may raise exception)
            try:
                if response.text:
                    return response.text
            except Exception:
                pass
            
            # If no valid response, return empty JSON
            logger.warning("Gemini returned empty response, using defaults")
            return "{}"
            
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return "{}"
    
    def _clean_json_response(self, response: str) -> str:
        """Clean JSON response by removing markdown formatting"""
        cleaned_response = response.strip()
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:]
        if cleaned_response.startswith('```'):
            cleaned_response = cleaned_response[3:]
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3]
        
        return cleaned_response.strip()
    
    def _fix_image_orientation(self, image: Image.Image) -> Image.Image:
        """
        Fix image orientation based on EXIF data to prevent rotation issues
        """
        try:
            # Use ImageOps.exif_transpose to automatically fix orientation
            image = ImageOps.exif_transpose(image)
            logger.info("Image orientation corrected based on EXIF data")
        except Exception as e:
            logger.warning(f"Could not fix image orientation: {e}")
        return image

