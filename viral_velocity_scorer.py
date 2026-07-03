import os
import base64
import json
import logging
from typing import Dict, List, Tuple, Optional
import openai
from PIL import Image
import io
from dotenv import load_dotenv
from content_moderator import ContentModerator
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('viral_velocity.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ViralVelocityScorer:
    """
    ai_image_scorer Image Scorer using Google Gemini Flash (primary) with OpenAI fallback
    Implements the 4-pillar scoring system for social media images with personalization
    Optimized for SPEED using Gemini Flash and image resizing
    """
    
    # Maximum image dimension for scoring (resize larger images for speed)
    MAX_SCORING_DIMENSION = 1536
    
    def __init__(self):
        """Initialize the scorer with Gemini Flash (primary) and OpenAI (fallback)"""
        logger.info("Initializing ViralVelocityScorer...")
        
        # Initialize Gemini Flash (PRIMARY - faster)
        gemini_key = os.getenv('GEMINI_API_KEY')
        self.gemini_client = None
        if gemini_key:
            try:
                genai.configure(api_key=gemini_key)
                self.gemini_client = genai.GenerativeModel('gemini-2.5-flash')
                logger.info("✅ Gemini 2.5 Flash initialized (PRIMARY scorer - fast)")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini Flash: {e}")
        
        # Initialize OpenAI (FALLBACK)
        api_key = os.getenv('OPENAI_API_KEY')
        self.openai_client = None
        if api_key:
            try:
                self.openai_client = openai.OpenAI(api_key=api_key)
                logger.info("✅ OpenAI client initialized (FALLBACK scorer)")
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI client: {e}")
        
        # Ensure at least one scorer is available
        if not self.gemini_client and not self.openai_client:
            raise ValueError("No AI scoring service available (need GEMINI_API_KEY or OPENAI_API_KEY)")
        
        # For backward compatibility
        self.client = self.openai_client
        
        # Scoring weights as per project specification
        self.weights = {
            'definition': 0.25,
            'layout': 0.25,
            'mood': 0.30,
            'vibe_check': 0.20
        }
        logger.info(f"Scoring weights initialized: {self.weights}")
        
        # Initialize content moderator
        logger.info("Initializing content moderator...")
        self.content_moderator = ContentModerator()
        logger.info("ViralVelocityScorer initialization complete")
    
    def _resize_for_scoring(self, image: Image) -> Image:
        """
        Resize image for faster AI scoring (doesn't affect quality, just speed)
        Large images are resized to max 1536px while maintaining aspect ratio
        """
        width, height = image.size
        max_dim = max(width, height)
        
        if max_dim <= self.MAX_SCORING_DIMENSION:
            return image  # Already small enough
        
        # Calculate new dimensions maintaining aspect ratio
        ratio = self.MAX_SCORING_DIMENSION / max_dim
        new_width = int(width * ratio)
        new_height = int(height * ratio)
        
        logger.info(f"⚡ Resizing image for scoring: {width}x{height} -> {new_width}x{new_height}")
        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    def analyze_image(self, image_path: str, user_preferences: Optional[Dict] = None) -> Dict:
        """
        Analyze an image and return comprehensive scoring (legacy method)
        """
        logger.info(f"Starting legacy image analysis for: {image_path}")
        return self.analyze_image_efficient(image_path, user_preferences)
    
    def analyze_image_efficient(self, image_path: str, user_preferences: Optional[Dict] = None, skip_moderation: bool = False) -> Dict:
        """
        Analyze an image more efficiently by combining multiple analyses into fewer API calls
        Now supports user preferences for personalized scoring
        
        Args:
            image_path: Path to the image file
            user_preferences: User preferences for personalized scoring
            skip_moderation: If True, skip content moderation (for pre-moderated enhanced images)
        """
        logger.info(f"Starting efficient image analysis for: {image_path}")
        if user_preferences:
            logger.info(f"User preferences: {user_preferences}")
        else:
            logger.info("No user preferences provided, using generic scoring")
        
        try:
            # Load and prepare image
            logger.info("Loading image...")
            image = Image.open(image_path)
            logger.info(f"Image loaded successfully. Size: {image.size}, Mode: {image.mode}")
            
            # Content Safety & Moderation Check (can be skipped for enhanced images)
            if skip_moderation:
                logger.info("⚡ Skipping content moderation (pre-moderated enhanced image)")
                is_safe = True
                moderation_result = {'status': 'skipped', 'reason': 'pre-moderated enhanced image'}
            else:
                logger.info("Performing content safety check...")
                is_safe, moderation_result = self.content_moderator.check_content_safety(image_path)
            
            if not is_safe:
                logger.warning(f"Content rejected due to: {moderation_result['rejection_reason']}")
                return {
                    'status': 'rejected',
                    'message': 'Image content was flagged as inappropriate',
                    'rejection_reason': moderation_result['rejection_reason'],
                    'moderation_details': moderation_result,
                    'final_score': 0,
                    'recommendations': [
                        'Please upload a different image that complies with our content guidelines',
                        'Ensure the image doesn\'t contain inappropriate, violent, or graphic content',
                        'Consider using images that are suitable for social media platforms'
                    ]
                }
            
            logger.info("Content safety check passed - proceeding with scoring")
            
            # Get ALL data in ONE API call (scores, sub-scores, details, feedback, recommendations)
            logger.info("Getting complete analysis in a single API call...")
            complete_result = self._get_complete_analysis(image, user_preferences)
            
            # Calculate weighted final score
            logger.info("Calculating weighted final score...")
            final_score = (
                complete_result['definition_score'] * self.weights['definition'] +
                complete_result['layout_score'] * self.weights['layout'] +
                complete_result['mood_score'] * self.weights['mood'] +
                complete_result['vibe_check_score'] * self.weights['vibe_check']
            )
            # Round immediately to 1 decimal place
            final_score = round(final_score, 1)
            logger.info(f"Final weighted score: {final_score}")
            
            result = {
                'final_score': final_score,
                'definition': {
                    'score': complete_result['definition_score'],
                    'weight': self.weights['definition'],
                    'weight_percent': '25%',
                    'details': complete_result.get('definition_details', ''),
                    'sub_scores': complete_result.get('definition_sub_scores', {}),
                    'feedback': complete_result.get('definition_feedback', '')
                },
                'layout': {
                    'score': complete_result['layout_score'],
                    'weight': self.weights['layout'],
                    'weight_percent': '25%',
                    'details': complete_result.get('layout_details', ''),
                    'sub_scores': complete_result.get('layout_sub_scores', {}),
                    'feedback': complete_result.get('layout_feedback', '')
                },
                'mood': {
                    'score': complete_result['mood_score'],
                    'weight': self.weights['mood'],
                    'weight_percent': '30%',
                    'details': complete_result.get('mood_details', ''),
                    'sub_scores': complete_result.get('mood_sub_scores', {}),
                    'feedback': complete_result.get('mood_feedback', '')
                },
                'vibe_check': {
                    'score': complete_result['vibe_check_score'],
                    'weight': self.weights['vibe_check'],
                    'weight_percent': '20%',
                    'details': complete_result.get('vibe_check_details', ''),
                    'sub_scores': complete_result.get('vibe_check_sub_scores', {}),
                    'feedback': complete_result.get('vibe_check_feedback', '')
                },
                'content_moderation': {
                    'status': 'passed',
                    'details': moderation_result
                }
            }
            
            logger.info(f"Efficient analysis complete. Final score: {result['final_score']}/100")
            return result
            
        except Exception as e:
            logger.error(f"Efficient analysis failed with error: {str(e)}", exc_info=True)
            return {'error': f'Analysis failed: {str(e)}'}
    
    def _get_definition_score(self, image: Image) -> float:
        """Get Definition Score (25% weight)"""
        logger.info("Starting Definition Score analysis...")
        
        prompt = """
        Analyze this image for definition quality. Consider:
        1. Sharpness & Focus (0-25 points): Is the image sharp and well-focused?
        2. Resolution & Clarity (0-25 points): Is the image clear and high-resolution?
        3. Image Noise (0-20 points): Is the image free from noise and artifacts?
        4. Dynamic Range (0-15 points): Are highlights and shadows well-balanced?
        5. Color Fidelity (0-15 points): Are colors natural and well-balanced?
        
        Return ONLY a raw JSON object (no markdown formatting, no code blocks) with:
        {
            "score": [0-100],
            "sharpness_focus": [0-25],
            "resolution_clarity": [0-25], 
            "noise": [0-20],
            "dynamic_range": [0-15],
            "color_fidelity": [0-15],
            "reasoning": "brief explanation"
        }
        """
        
        logger.info("Sending Definition prompt to OpenAI...")
        response = self._get_ai_response(image, prompt)
        logger.info(f"OpenAI Definition response: {response}")
        
        try:
            cleaned_response = self._clean_json_response(response)
            logger.info(f"Cleaned response: {cleaned_response}")
            
            result = json.loads(cleaned_response)
            score = result.get('score', 0)
            logger.info(f"Definition Score parsed successfully: {score}")
            return score
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Definition JSON: {e}")
            logger.error(f"Raw response: {response}")
            logger.error(f"Cleaned response: {cleaned_response}")
            return 50  # Default score if parsing fails
    
    def _get_layout_score(self, image: Image) -> float:
        """Get Layout Score (25% weight)"""
        logger.info("Starting Layout Score analysis...")
        
        prompt = """
        Analyze this image for layout quality. Consider:
        1. Rule of Thirds (0-25 points): Is the subject positioned according to rule of thirds?
        2. Leading Lines (0-20 points): Do lines guide the eye toward the subject?
        3. Balance & Symmetry (0-20 points): Is the composition balanced?
        4. Depth & Framing (0-20 points): Does the image have good depth and framing?
        5. Subject Isolation (0-15 points): Is the subject well-isolated and prominent?
        
        Return ONLY a raw JSON object (no markdown formatting, no code blocks) with:
        {
            "score": [0-100],
            "rule_of_thirds": [0-25],
            "leading_lines": [0-20],
            "balance_symmetry": [0-20],
            "depth_framing": [0-20],
            "subject_isolation": [0-15],
            "reasoning": "brief explanation"
        }
        """
        
        logger.info("Sending Layout prompt to OpenAI...")
        response = self._get_ai_response(image, prompt)
        logger.info(f"OpenAI Layout response: {response}")
        
        try:
            cleaned_response = self._clean_json_response(response)
            logger.info(f"Cleaned response: {cleaned_response}")
            
            result = json.loads(cleaned_response)
            score = result.get('score', 0)
            logger.info(f"Layout Score parsed successfully: {score}")
            return score
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Layout JSON: {e}")
            logger.error(f"Raw response: {response}")
            logger.error(f"Cleaned response: {cleaned_response}")
            return 50
    
    def _get_mood_score(self, image: Image) -> float:
        """Get Mood Score (30% weight)"""
        logger.info("Starting Mood Score analysis...")
        
        prompt = """
        Analyze this image for mood and engagement potential. Consider:
        1. Presence of Faces (0-30 points): Are there faces and are they engaging?
        2. Emotional Resonance (0-25 points): Does the image evoke emotions?
        3. Color Psychology (0-25 points): Do colors create the right mood?
        4. Storytelling (0-20 points): Does the image tell a story?
        
        Return ONLY a raw JSON object (no markdown formatting, no code blocks) with:
        {
            "score": [0-100],
            "faces": [0-30],
            "emotional_resonance": [0-25],
            "color_psychology": [0-25],
            "storytelling": [0-20],
            "reasoning": "brief explanation"
        }
        """
        
        logger.info("Sending Mood prompt to OpenAI...")
        response = self._get_ai_response(image, prompt)
        logger.info(f"OpenAI Mood response: {response}")
        
        try:
            cleaned_response = self._clean_json_response(response)
            logger.info(f"Cleaned response: {cleaned_response}")
            
            result = json.loads(cleaned_response)
            score = result.get('score', 0)
            logger.info(f"Mood Score parsed successfully: {score}")
            return score
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Mood JSON: {e}")
            logger.error(f"Raw response: {response}")
            logger.error(f"Cleaned response: {cleaned_response}")
            return 50
    
    def _get_vibe_check_score(self, image: Image) -> float:
        """Get Vibe Check Score (20% weight)"""
        logger.info("Starting Vibe Check Score analysis...")
        
        prompt = """
        Analyze this image for vibe check and trend alignment. Consider:
        1. Aesthetic Alignment (0-60 points): Does it align with current visual trends?
        2. Authenticity Index (0-40 points): Does it feel authentic and genuine?
        
        Return ONLY a raw JSON object (no markdown formatting, no code blocks) with:
        {
            "score": [0-100],
            "aesthetic_alignment": [0-60],
            "authenticity": [0-40],
            "detected_aesthetic": "e.g., Y2K, Maximalist, Minimalist, etc.",
            "reasoning": "brief explanation"
        }
        """
        
        logger.info("Sending Vibe Check prompt to OpenAI...")
        response = self._get_ai_response(image, prompt)
        logger.info(f"OpenAI Vibe Check response: {response}")
        
        try:
            cleaned_response = self._clean_json_response(response)
            logger.info(f"Cleaned response: {cleaned_response}")
            
            result = json.loads(cleaned_response)
            score = result.get('score', 0)
            logger.info(f"Vibe Check Score parsed successfully: {score}")
            return score
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Vibe Check JSON: {e}")
            logger.error(f"Raw response: {response}")
            logger.error(f"Cleaned response: {cleaned_response}")
            return 50
    
    def _get_complete_analysis(self, image: Image, user_preferences: Optional[Dict] = None) -> Dict:
        """Get ALL analysis data in a SINGLE API call - scores, sub-scores, details, feedback, and recommendations"""
        
        # Build personalized prompt based on user preferences
        if user_preferences:
            aesthetic = user_preferences.get('aesthetic', 'General')
            niche = user_preferences.get('niche', 'General')
            target_audience = user_preferences.get('target_audience', 'General')
            content_type = user_preferences.get('content_type', 'Social Media Post')
            brand_voice = user_preferences.get('brand_voice', 'Neutral')
            
            prompt = f"""
            Analyze this image completely for social media scoring with personalized criteria.
            
            USER PREFERENCES:
            - Aesthetic: {aesthetic}
            - Niche: {niche}
            - Target Audience: {target_audience}
            - Content Type: {content_type}
            - Brand Voice: {brand_voice}
            
            Provide a COMPLETE analysis including:
            1. Main scores (0-100) for each of the 4 pillars
            2. Sub-scores (0-100) for each component within each pillar (as specified below)
            3. Brief detailed analysis text for each pillar
            4. Specific feedback/coaching tip for each pillar
            5. Three actionable recommendations to improve the image
            
            Return ONLY a raw JSON object (no markdown, no code blocks):
            {{
                "definition_score": [0-100],
                "definition_sub_scores": {{
                    "sharpness_focus": [0-100],
                    "resolution_clarity": [0-100],
                    "image_noise": [0-100],
                    "dynamic_range": [0-100],
                    "color_fidelity": [0-100]
                }},
                "definition_details": "2-3 sentence analysis of definition/technical quality",
                "definition_feedback": "one specific tip to improve definition",
                
                "layout_score": [0-100],
                "layout_sub_scores": {{
                    "rule_of_thirds": [0-100],
                    "leading_lines": [0-100],
                    "balance_symmetry": [0-100],
                    "depth_framing": [0-100],
                    "subject_isolation": [0-100]
                }},
                "layout_details": "2-3 sentence analysis of layout/composition",
                "layout_feedback": "one specific tip to improve layout",
                
                "mood_score": [0-100],
                "mood_sub_scores": {{
                    "presence_of_faces": [0-100],
                    "emotional_resonance": [0-100],
                    "color_psychology": [0-100],
                    "storytelling": [0-100]
                }},
                "mood_details": "2-3 sentence analysis for {target_audience} engagement",
                "mood_feedback": "one specific tip to boost mood/engagement",
                
                "vibe_check_score": [0-100],
                "vibe_check_sub_scores": {{
                    "aesthetic_alignment": [0-100],
                    "authenticity_index": [0-100]
                }},
                "vibe_check_details": "2-3 sentence analysis of {aesthetic} aesthetic alignment for {niche}",
                "vibe_check_feedback": "one specific tip to improve vibe check/trend alignment",
                
                "recommendations": ["recommendation 1", "recommendation 2", "recommendation 3"]
            }}
            """
        else:
            prompt = """
            Analyze this image completely for social media scoring.
            
            Provide a COMPLETE analysis including:
            1. Main scores (0-100) for each of the 4 pillars
            2. Sub-scores (0-100) for each component within each pillar (as specified below)
            3. Brief detailed analysis text for each pillar
            4. Specific feedback/coaching tip for each pillar
            5. Three actionable recommendations to improve the image
            
            Return ONLY a raw JSON object (no markdown, no code blocks):
            {
                "definition_score": [0-100],
                "definition_sub_scores": {
                    "sharpness_focus": [0-100],
                    "resolution_clarity": [0-100],
                    "image_noise": [0-100],
                    "dynamic_range": [0-100],
                    "color_fidelity": [0-100]
                },
                "definition_details": "2-3 sentence analysis of definition/technical quality",
                "definition_feedback": "one specific tip to improve definition",
                
                "layout_score": [0-100],
                "layout_sub_scores": {
                    "rule_of_thirds": [0-100],
                    "leading_lines": [0-100],
                    "balance_symmetry": [0-100],
                    "depth_framing": [0-100],
                    "subject_isolation": [0-100]
                },
                "layout_details": "2-3 sentence analysis of layout/composition",
                "layout_feedback": "one specific tip to improve layout",
                
                "mood_score": [0-100],
                "mood_sub_scores": {
                    "presence_of_faces": [0-100],
                    "emotional_resonance": [0-100],
                    "color_psychology": [0-100],
                    "storytelling": [0-100]
                },
                "mood_details": "2-3 sentence analysis of mood/psychological engagement",
                "mood_feedback": "one specific tip to boost mood/engagement",
                
                "vibe_check_score": [0-100],
                "vibe_check_sub_scores": {
                    "aesthetic_alignment": [0-100],
                    "authenticity_index": [0-100]
                },
                "vibe_check_details": "2-3 sentence analysis of vibe check/trend alignment",
                "vibe_check_feedback": "one specific tip to improve vibe check",
                
                "recommendations": ["recommendation 1", "recommendation 2", "recommendation 3"]
            }
            """
        
        logger.info("Sending COMPLETE analysis prompt to OpenAI (single API call)...")
        response = self._get_ai_response(image, prompt)
        logger.info(f"OpenAI complete analysis response received: {len(response)} chars")
        
        try:
            cleaned_response = self._clean_json_response(response)
            result = json.loads(cleaned_response)
            
            # Ensure all required fields exist with defaults (matching spec)
            default_definition_sub = {
                'sharpness_focus': 50, 'resolution_clarity': 50, 
                'image_noise': 50, 'dynamic_range': 50, 'color_fidelity': 50
            }
            default_layout_sub = {
                'rule_of_thirds': 50, 'leading_lines': 50,
                'balance_symmetry': 50, 'depth_framing': 50, 'subject_isolation': 50
            }
            default_mood_sub = {
                'presence_of_faces': 50, 'emotional_resonance': 50,
                'color_psychology': 50, 'storytelling': 50
            }
            default_vibe_check_sub = {
                'aesthetic_alignment': 50, 'authenticity_index': 50
            }
            
            complete_data = {
                'definition_score': result.get('definition_score', 50),
                'definition_sub_scores': result.get('definition_sub_scores', default_definition_sub),
                'definition_details': result.get('definition_details', 'Definition analysis not available'),
                'definition_feedback': result.get('definition_feedback', ''),
                
                'layout_score': result.get('layout_score', 50),
                'layout_sub_scores': result.get('layout_sub_scores', default_layout_sub),
                'layout_details': result.get('layout_details', 'Layout analysis not available'),
                'layout_feedback': result.get('layout_feedback', ''),
                
                'mood_score': result.get('mood_score', 50),
                'mood_sub_scores': result.get('mood_sub_scores', default_mood_sub),
                'mood_details': result.get('mood_details', 'Mood analysis not available'),
                'mood_feedback': result.get('mood_feedback', ''),
                
                'vibe_check_score': result.get('vibe_check_score', 50),
                'vibe_check_sub_scores': result.get('vibe_check_sub_scores', default_vibe_check_sub),
                'vibe_check_details': result.get('vibe_check_details', 'Vibe check analysis not available'),
                'vibe_check_feedback': result.get('vibe_check_feedback', ''),
                
                'recommendations': result.get('recommendations', ['No recommendations available'])
            }
            
            logger.info(f"Complete analysis parsed successfully - scores: Definition={complete_data['definition_score']}, Layout={complete_data['layout_score']}, Mood={complete_data['mood_score']}, VibeCheck={complete_data['vibe_check_score']}")
            return complete_data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse complete analysis JSON: {e}")
            logger.error(f"Raw response: {response[:500]}...")
            # Return defaults matching spec
            return {
                'definition_score': 50,
                'definition_sub_scores': {'sharpness_focus': 50, 'resolution_clarity': 50, 'image_noise': 50, 'dynamic_range': 50, 'color_fidelity': 50},
                'definition_details': 'Analysis unavailable',
                'definition_feedback': '',
                'layout_score': 50,
                'layout_sub_scores': {'rule_of_thirds': 50, 'leading_lines': 50, 'balance_symmetry': 50, 'depth_framing': 50, 'subject_isolation': 50},
                'layout_details': 'Analysis unavailable',
                'layout_feedback': '',
                'mood_score': 50,
                'mood_sub_scores': {'presence_of_faces': 50, 'emotional_resonance': 50, 'color_psychology': 50, 'storytelling': 50},
                'mood_details': 'Analysis unavailable',
                'mood_feedback': '',
                'vibe_check_score': 50,
                'vibe_check_sub_scores': {'aesthetic_alignment': 50, 'authenticity_index': 50},
                'vibe_check_details': 'Analysis unavailable',
                'vibe_check_feedback': '',
                'recommendations': ['Please try again']
            }
    
    def _get_all_scores_combined(self, image: Image, user_preferences: Optional[Dict] = None) -> Dict:
        """Get all scores in a single API call with personalization and detailed sub-scores (LEGACY - use _get_complete_analysis instead)"""
        
        # Build personalized prompt based on user preferences
        if user_preferences:
            aesthetic = user_preferences.get('aesthetic', 'General')
            niche = user_preferences.get('niche', 'General')
            target_audience = user_preferences.get('target_audience', 'General')
            content_type = user_preferences.get('content_type', 'Social Media Post')
            brand_voice = user_preferences.get('brand_voice', 'Neutral')
            
            prompt = f"""
            Analyze this image for social media scoring with personalized criteria.
            
            USER PREFERENCES:
            - Aesthetic: {aesthetic}
            - Niche: {niche}
            - Target Audience: {target_audience}
            - Content Type: {content_type}
            - Brand Voice: {brand_voice}
            
            Score this image based on how well it aligns with the user's specific preferences above.
            Provide detailed sub-scores for each category.
            
            Return ONLY a raw JSON object (no markdown formatting, no code blocks) with:
            {{
                "definition_score": [0-100],
                "definition_sub_scores": {{
                    "sharpness_focus": [0-100],
                    "resolution_clarity": [0-100],
                    "image_noise": [0-100],
                    "dynamic_range": [0-100],
                    "color_fidelity": [0-100]
                }},
                "definition_feedback": "brief specific feedback for definition improvements",
                "layout_score": [0-100],
                "layout_sub_scores": {{
                    "rule_of_thirds": [0-100],
                    "leading_lines": [0-100],
                    "balance_symmetry": [0-100],
                    "depth_framing": [0-100],
                    "subject_isolation": [0-100]
                }},
                "layout_feedback": "brief specific feedback for layout improvements",
                "mood_score": [0-100],
                "mood_sub_scores": {{
                    "presence_of_faces": [0-100],
                    "emotional_resonance": [0-100],
                    "color_psychology": [0-100],
                    "storytelling": [0-100]
                }},
                "mood_feedback": "brief specific feedback for mood/engagement targeting {target_audience}",
                "vibe_check_score": [0-100],
                "vibe_check_sub_scores": {{
                    "aesthetic_alignment": [0-100],
                    "authenticity_index": [0-100]
                }},
                "vibe_check_feedback": "brief specific feedback for {aesthetic} aesthetic alignment in {niche}"
            }}
            """
        else:
            prompt = """
            Analyze this image for social media scoring. Provide scores for all four categories with detailed sub-scores.
            
            Return ONLY a raw JSON object (no markdown formatting, no code blocks) with:
            {
                "definition_score": [0-100],
                "definition_sub_scores": {
                    "sharpness_focus": [0-100],
                    "resolution_clarity": [0-100],
                    "image_noise": [0-100],
                    "dynamic_range": [0-100],
                    "color_fidelity": [0-100]
                },
                "definition_feedback": "brief specific feedback for definition improvements",
                "layout_score": [0-100],
                "layout_sub_scores": {
                    "rule_of_thirds": [0-100],
                    "leading_lines": [0-100],
                    "balance_symmetry": [0-100],
                    "depth_framing": [0-100],
                    "subject_isolation": [0-100]
                },
                "layout_feedback": "brief specific feedback for layout improvements",
                "mood_score": [0-100],
                "mood_sub_scores": {
                    "presence_of_faces": [0-100],
                    "emotional_resonance": [0-100],
                    "color_psychology": [0-100],
                    "storytelling": [0-100]
                },
                "mood_feedback": "brief specific feedback for mood/engagement",
                "vibe_check_score": [0-100],
                "vibe_check_sub_scores": {
                    "aesthetic_alignment": [0-100],
                    "authenticity_index": [0-100]
                },
                "vibe_check_feedback": "brief specific feedback for vibe check/trend alignment"
            }
            """
        
        logger.info("Sending combined scoring prompt to OpenAI...")
        response = self._get_ai_response(image, prompt)
        logger.info(f"OpenAI combined scoring response: {response}")
        
        try:
            cleaned_response = self._clean_json_response(response)
            logger.info(f"Cleaned combined response: {cleaned_response}")
            
            result = json.loads(cleaned_response)
            
            # Default sub-scores structure
            default_definition_sub = {
                'sharpness_focus': 50,
                'resolution_clarity': 50,
                'image_noise': 50,
                'dynamic_range': 50,
                'color_fidelity': 50
            }
            default_layout_sub = {
                'rule_of_thirds': 50,
                'leading_lines': 50,
                'balance_symmetry': 50,
                'depth_framing': 50,
                'subject_isolation': 50
            }
            default_mood_sub = {
                'presence_of_faces': 50,
                'emotional_resonance': 50,
                'color_psychology': 50,
                'storytelling': 50
            }
            default_vibe_check_sub = {
                'aesthetic_alignment': 50,
                'authenticity_index': 50
            }
            
            scores = {
                'definition_score': result.get('definition_score', 50),
                'definition_sub_scores': result.get('definition_sub_scores', default_definition_sub),
                'definition_feedback': result.get('definition_feedback', 'Definition analysis not available'),
                'layout_score': result.get('layout_score', 50),
                'layout_sub_scores': result.get('layout_sub_scores', default_layout_sub),
                'layout_feedback': result.get('layout_feedback', 'Layout analysis not available'),
                'mood_score': result.get('mood_score', 50),
                'mood_sub_scores': result.get('mood_sub_scores', default_mood_sub),
                'mood_feedback': result.get('mood_feedback', 'Mood analysis not available'),
                'vibe_check_score': result.get('vibe_check_score', 50),
                'vibe_check_sub_scores': result.get('vibe_check_sub_scores', default_vibe_check_sub),
                'vibe_check_feedback': result.get('vibe_check_feedback', 'Vibe check analysis not available')
            }
            logger.info(f"Combined scores parsed successfully: {scores}")
            return scores
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse combined scores JSON: {e}")
            logger.error(f"Raw response: {response}")
            return {
                'definition_score': 50,
                'definition_sub_scores': {'sharpness_focus': 50, 'resolution_clarity': 50, 'image_noise': 50, 'dynamic_range': 50, 'color_fidelity': 50},
                'definition_feedback': 'Definition analysis not available',
                'layout_score': 50,
                'layout_sub_scores': {'rule_of_thirds': 50, 'leading_lines': 50, 'balance_symmetry': 50, 'depth_framing': 50, 'subject_isolation': 50},
                'layout_feedback': 'Layout analysis not available',
                'mood_score': 50,
                'mood_sub_scores': {'presence_of_faces': 50, 'emotional_resonance': 50, 'color_psychology': 50, 'storytelling': 50},
                'mood_feedback': 'Mood analysis not available',
                'vibe_check_score': 50,
                'vibe_check_sub_scores': {'aesthetic_alignment': 50, 'authenticity_index': 50},
                'vibe_check_feedback': 'Vibe check analysis not available'
            }
    
    def _get_all_details_combined(self, image: Image, user_preferences: Optional[Dict] = None) -> Dict:
        """Get all detailed analyses in a single API call with personalization (LEGACY - use _get_complete_analysis instead)"""
        
        # Build personalized prompt based on user preferences
        if user_preferences:
            aesthetic = user_preferences.get('aesthetic', 'General')
            niche = user_preferences.get('niche', 'General')
            target_audience = user_preferences.get('target_audience', 'General')
            
            prompt = f"""
            Provide detailed analysis for this image in four categories, considering the user's preferences:
            - Aesthetic: {aesthetic}
            - Niche: {niche}
            - Target Audience: {target_audience}
            
            Return as a JSON object with:
            
            - definition_details: Brief definition analysis focusing on sharpness, noise, and color quality
            - layout_details: Brief layout analysis focusing on framing, balance, and visual flow
            - mood_details: Brief mood analysis focusing on emotional impact and engagement potential for {target_audience}
            - vibe_check_details: Brief vibe check analysis focusing on alignment with {aesthetic} aesthetic for {niche} content
            
            Return ONLY a raw JSON object (no markdown formatting, no code blocks) with:
            {{
                "definition_details": "brief definition analysis",
                "layout_details": "brief layout analysis", 
                "mood_details": "brief mood analysis",
                "vibe_check_details": "brief vibe check analysis"
            }}
            """
        else:
            prompt = """
            Provide detailed analysis for this image in four categories. Return as a JSON object with:
            
            - definition_details: Brief definition analysis focusing on sharpness, noise, and color quality
            - layout_details: Brief layout analysis focusing on framing, balance, and visual flow
            - mood_details: Brief mood analysis focusing on emotional impact and engagement potential
            - vibe_check_details: Brief vibe check analysis focusing on current aesthetic alignment and cultural relevance
            
            Return ONLY a raw JSON object (no markdown formatting, no code blocks) with:
            {
                "definition_details": "brief definition analysis",
                "layout_details": "brief layout analysis", 
                "mood_details": "brief mood analysis",
                "vibe_check_details": "brief vibe check analysis"
            }
            """
        
        logger.info("Sending combined details prompt to OpenAI...")
        response = self._get_ai_response(image, prompt)
        logger.info(f"OpenAI combined details response: {response}")
        
        try:
            cleaned_response = self._clean_json_response(response)
            logger.info(f"Cleaned combined details response: {cleaned_response}")
            
            result = json.loads(cleaned_response)
            details = {
                'definition_details': result.get('definition_details', 'Definition analysis not available'),
                'layout_details': result.get('layout_details', 'Layout analysis not available'),
                'mood_details': result.get('mood_details', 'Mood analysis not available'),
                'vibe_check_details': result.get('vibe_check_details', 'Vibe check analysis not available')
            }
            logger.info(f"Combined details parsed successfully")
            return details
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse combined details JSON: {e}")
            logger.error(f"Raw response: {response}")
            return {
                'definition_details': 'Definition analysis not available',
                'layout_details': 'Layout analysis not available',
                'mood_details': 'Mood analysis not available',
                'vibe_check_details': 'Vibe check analysis not available'
            }
    
    def _clean_json_response(self, response: str) -> str:
        """Clean JSON response by removing markdown formatting"""
        cleaned_response = response.strip()
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:]  # Remove ```json
        if cleaned_response.startswith('```'):
            cleaned_response = cleaned_response[3:]  # Remove ```
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3]  # Remove trailing ```
        
        return cleaned_response.strip()
    
    def _get_ai_response(self, image: Image, prompt: str) -> str:
        """
        Get response from AI - uses Gemini Flash (fast) as primary, OpenAI as fallback
        Also resizes image for faster processing
        """
        # Resize image for faster scoring
        scoring_image = self._resize_for_scoring(image)
        
        # Try Gemini Flash first (faster)
        if self.gemini_client:
            try:
                logger.info("⚡ Using Gemini Flash for fast scoring...")
                
                # Convert PIL image to bytes for Gemini
                img_buffer = io.BytesIO()
                scoring_image.save(img_buffer, format='JPEG', quality=85)
                img_bytes = img_buffer.getvalue()
                
                response = self.gemini_client.generate_content([
                    prompt,
                    {"mime_type": "image/jpeg", "data": img_bytes}
                ])
                
                if response and response.text:
                    logger.info(f"⚡ Gemini Flash response received. Length: {len(response.text)} characters")
                    return response.text
                else:
                    logger.warning("Gemini returned empty response, falling back to OpenAI")
            except Exception as e:
                logger.warning(f"Gemini Flash error: {e}, falling back to OpenAI")
        
        # Fallback to OpenAI
        return self._get_openai_response(scoring_image, prompt)
    
    def _get_openai_response(self, image: Image, prompt: str) -> str:
        """Get response from OpenAI GPT-4 Vision (fallback)"""
        if not self.openai_client:
            logger.error("OpenAI client not available")
            return "{}"
            
        logger.info("Preparing image for OpenAI API...")
        
        try:
            # Convert PIL image to base64
            img_buffer = io.BytesIO()
            image.save(img_buffer, format='JPEG')
            img_str = base64.b64encode(img_buffer.getvalue()).decode()
            logger.info(f"Image converted to base64. Size: {len(img_str)} characters")
            
            logger.info("Sending request to OpenAI API...")
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{img_str}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=2000
            )
            
            content = response.choices[0].message.content
            logger.info(f"OpenAI API response received. Length: {len(content)} characters")
            
            return content
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}", exc_info=True)
            return "{}"
    
    def _get_definition_details(self, image: Image) -> str:
        """Get detailed definition analysis"""
        logger.info("Getting detailed definition analysis...")
        prompt = "Provide a brief definition analysis of this image focusing on sharpness, noise, and color quality."
        response = self._get_ai_response(image, prompt)
        logger.info(f"Definition details received: {len(response)} characters")
        return response
    
    def _get_layout_details(self, image: Image) -> str:
        """Get detailed layout analysis"""
        logger.info("Getting detailed layout analysis...")
        prompt = "Provide a brief layout analysis of this image focusing on framing, balance, and visual flow."
        response = self._get_ai_response(image, prompt)
        logger.info(f"Layout details received: {len(response)} characters")
        return response
    
    def _get_mood_details(self, image: Image) -> str:
        """Get detailed mood analysis"""
        logger.info("Getting detailed mood analysis...")
        prompt = "Provide a brief mood analysis of this image focusing on emotional impact and engagement potential."
        response = self._get_ai_response(image, prompt)
        logger.info(f"Mood details received: {len(response)} characters")
        return response
    
    def _get_vibe_check_details(self, image: Image) -> str:
        """Get detailed vibe check analysis"""
        logger.info("Getting detailed vibe check analysis...")
        prompt = "Provide a brief vibe check analysis of this image focusing on current aesthetic alignment and cultural relevance."
        response = self._get_ai_response(image, prompt)
        logger.info(f"Vibe check details received: {len(response)} characters")
        return response
    
    def _get_recommendations(self, image: Image, final_score: float, user_preferences: Optional[Dict] = None) -> List[str]:
        """Get improvement recommendations based on score"""
        logger.info(f"Generating recommendations for score: {final_score}")
        
        # Build personalized prompt based on user preferences
        if user_preferences:
            aesthetic = user_preferences.get('aesthetic', 'General')
            niche = user_preferences.get('niche', 'General')
            target_audience = user_preferences.get('target_audience', 'General')
            content_type = user_preferences.get('content_type', 'Social Media Post')
            brand_voice = user_preferences.get('brand_voice', 'Neutral')
            
            prompt = f"""
            This image received a social media score of {final_score}/100. 
            Provide 3 specific, actionable recommendations to improve the score, considering the user's preferences:
            - Aesthetic: {aesthetic}
            - Niche: {niche}
            - Target Audience: {target_audience}
            - Content Type: {content_type}
            - Brand Voice: {brand_voice}
            Focus on practical tips that could be implemented quickly.
            """
        else:
            prompt = f"""
            This image received a social media score of {final_score}/100. 
            Provide 3 specific, actionable recommendations to improve the score.
            Focus on practical tips that could be implemented quickly.
            """
        
        response = self._get_ai_response(image, prompt)
        logger.info(f"Recommendations response: {response}")
        
        # Parse recommendations more intelligently
        lines = response.split('\n')
        recommendations = []
        current_recommendation = ""
        
        for line in lines:
            line = line.strip()
            # Look for numbered recommendations (1., 2., 3., etc.)
            if line and (line.startswith('1.') or line.startswith('2.') or line.startswith('3.') or 
                        line.startswith('**1.') or line.startswith('**2.') or line.startswith('**3.')):
                # If we have a previous recommendation, save it
                if current_recommendation:
                    recommendations.append(current_recommendation.strip())
                
                # Start new recommendation
                clean_line = line.replace('**', '').strip()
                if clean_line.startswith('1.'):
                    current_recommendation = clean_line[2:].strip()
                elif clean_line.startswith('2.'):
                    current_recommendation = clean_line[2:].strip()
                elif clean_line.startswith('3.'):
                    current_recommendation = clean_line[2:].strip()
                else:
                    current_recommendation = clean_line
            elif line and current_recommendation and not line.startswith('To improve') and not line.startswith('Implementing'):
                # Continue building the current recommendation
                current_recommendation += " " + line
        
        # Add the last recommendation
        if current_recommendation:
            recommendations.append(current_recommendation.strip())
        
        # If we didn't find numbered recommendations, try a simpler approach
        if len(recommendations) < 3:
            recommendations = [line.strip() for line in lines if line.strip() and 
                             not line.startswith('To improve') and 
                             not line.startswith('Implementing') and
                             len(line.strip()) > 20][:3]
        
        logger.info(f"Parsed {len(recommendations)} recommendations")
        
        return recommendations

# Test function
def test_scorer():
    """Test the scorer with a sample image"""
    logger.info("Starting test_scorer function...")
    scorer = ViralVelocityScorer()
    
    # You'll need to provide a test image path
    test_image_path = "test_image.jpg"  # Replace with actual image path
    
    if os.path.exists(test_image_path):
        logger.info(f"Test image found: {test_image_path}")
        result = scorer.analyze_image(test_image_path)
        logger.info("Test completed successfully")
        print(json.dumps(result, indent=2))
    else:
        logger.warning(f"Test image not found: {test_image_path}")
        print(f"Test image not found: {test_image_path}")
        print("Please provide a test image to run the scorer.")

if __name__ == "__main__":
    test_scorer()
